"""Batch entry point: python -m src.cli --source data/raw/Sample - Superstore.csv"""
from __future__ import annotations
import argparse, hashlib, json, logging, os, smtplib, sys, uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from src.data.pipeline import load_csv
from src.analytics.metrics import kpis
from src.reporting.reports import build_report, save_reports

def configure_logging():
    Path("reports").mkdir(exist_ok=True)
    logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)s %(levelname)s %(message)s",
       handlers=[logging.StreamHandler(),logging.FileHandler("reports/pipeline.log",encoding="utf-8")])

def deliver(paths, anomalies):
    recipient=os.getenv("REPORT_EMAIL_TO")
    if not recipient: return False
    required=("SMTP_HOST","SMTP_PORT","SMTP_USER","SMTP_PASSWORD","REPORT_EMAIL_FROM")
    missing=[key for key in required if not os.getenv(key)]
    if missing: raise RuntimeError("Email delivery configuration missing: "+", ".join(missing))
    message=EmailMessage(); message["Subject"]="RetailIQ scheduled management report"; message["From"]=os.environ["REPORT_EMAIL_FROM"]; message["To"]=recipient
    high=[a for a in anomalies if a["severity"]=="high"]
    alert_enabled=os.getenv("EMAIL_HIGH_SEVERITY_ALERTS","true").lower() in {"1","true","yes"}
    details="\n".join(f"- {a['metric']} / {a['dimension']} {a['group']}: {a['observed']} (baseline {a['baseline']})" for a in high) if alert_enabled else ""
    message.set_content(f"Attached are the RetailIQ management report files. High severity anomalies: {len(high)}."+("\n\nHigh severity alerts:\n"+details if details else ""))
    for path in paths.values(): message.add_attachment(path.read_bytes(),maintype="application",subtype="octet-stream",filename=path.name)
    with smtplib.SMTP(os.environ["SMTP_HOST"],int(os.environ["SMTP_PORT"]),timeout=30) as server:
        server.starttls(); server.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"]); server.send_message(message)
    return True

def run(source, output_dir="reports", email=False, frequency="daily"):
    load_dotenv()
    started=datetime.now(timezone.utc); run_id=str(uuid.uuid4()); logging.info("Starting run_id=%s source=%s",run_id,source)
    try:
        frame,quality=load_csv(source)
        quarantine=frame[frame.quality_rejected].copy()
        quarantine_path=Path(output_dir)/"retailiq_quarantine.csv"
        Path(output_dir).mkdir(parents=True,exist_ok=True)
        quarantine.to_csv(quarantine_path,index=False,encoding="utf-8-sig")
        fingerprint=hashlib.sha256(Path(source).read_bytes()).hexdigest()
        valid=frame[~frame.quality_rejected].copy()
        summary={"source":str(source),"source_fingerprint":fingerprint,"started_at":started.isoformat(),"frequency":frequency,"kpis":kpis(valid)}
        if os.getenv("DATABASE_URL"):
            from src.database.postgres import persist_run
            result=persist_run(frame,quality,summary,fingerprint,run_id)
            if result.get("skipped"):
                logging.info("Source already processed; no duplicate load: %s",result["run_id"])
        previous_quality=None
        previous_path=Path(output_dir,"last_run.json")
        if previous_path.exists():
            try:
                prior=json.loads(previous_path.read_text(encoding="utf-8"))
                previous_quality={"rejected_rate":prior.get("rejected_rows",0)/max(prior.get("source_rows",0),1)}
            except (ValueError,OSError): logging.warning("Could not read previous run quality summary")
        report=build_report(frame,quality,generated_at=started.isoformat(),previous_quality=previous_quality)
        report["report_frequency"] = f"{frequency.title()} management report"
        paths=save_reports(report,output_dir)
        summary.update({"run_id":run_id,"status":"success","source_rows":quality["source_rows"],"valid_rows":quality["valid_rows"],"rejected_rows":quality["rejected_rows"],"duplicate_rows":quality["duplicate_rows"],"quarantine_file":str(quarantine_path),"report_files":{k:str(v) for k,v in paths.items()},"email_sent":deliver(paths,report["anomalies"]) if email else False})
        logging.info("Run completed: %s",json.dumps(summary,default=str))
        Path(output_dir,"last_run.json").write_text(json.dumps(summary,indent=2,default=str),encoding="utf-8")
        return summary
    except Exception as exc:
        logging.exception("Run failed run_id=%s",run_id)
        try:
            if os.getenv("DATABASE_URL"):
                from src.database.postgres import record_failed_run
                record_failed_run(run_id,source,exc,started_at=started)
        except Exception:
            logging.exception("Failed run could not be persisted to PostgreSQL")
        try:
            Path(output_dir).mkdir(parents=True,exist_ok=True)
            Path(output_dir,"last_run.json").write_text(json.dumps({"run_id":run_id,"status":"failed","source":str(source),"started_at":started.isoformat(),"error":str(exc)[:1000]},indent=2),encoding="utf-8")
        except OSError:
            logging.exception("Failed run summary could not be written")
        logging.error("%s",json.dumps({"run_id":run_id,"status":"failed","source":str(source),"error":str(exc)[:1000]}))
        if email and os.getenv("REPORT_EMAIL_TO"):
            try:
                message=EmailMessage(); message["Subject"]="RetailIQ pipeline failure"; message["From"]=os.environ["REPORT_EMAIL_FROM"]; message["To"]=os.environ["REPORT_EMAIL_TO"]; message.set_content(f"RetailIQ pipeline failed. Run ID: {run_id}. Check reports/pipeline.log.")
                with smtplib.SMTP(os.environ["SMTP_HOST"],int(os.environ["SMTP_PORT"]),timeout=30) as server:
                    server.starttls(); server.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"]); server.send_message(message)
            except Exception: logging.exception("Failure notification could not be sent")
        raise

def main(argv=None):
    parser=argparse.ArgumentParser(description="Run RetailIQ ingestion and management reporting")
    parser.add_argument("--source",default="data/raw/Sample - Superstore.csv")
    parser.add_argument("--output-dir",default="reports")
    parser.add_argument("--email",action="store_true",help="Send report or failure notification using SMTP environment configuration")
    parser.add_argument("--weekly",action="store_true",help="Generate the weekly management report")
    args=parser.parse_args(argv); configure_logging()
    try: run(args.source,args.output_dir,args.email,"weekly" if args.weekly else "daily")
    except Exception as exc: logging.error("Pipeline failed: %s",exc); return 1
    return 0
if __name__=="__main__": sys.exit(main())
