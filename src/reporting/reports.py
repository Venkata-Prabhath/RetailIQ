from __future__ import annotations
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import pandas as pd
from src.analytics.metrics import kpis, group_summary, period_comparison
from src.analytics.anomalies import detect_anomalies

def build_report(frame, quality, *, generated_at=None, previous_quality=None):
    valid = frame[~frame.get("quality_rejected", pd.Series(False, index=frame.index))].copy()
    dates = valid.order_date.dropna() if "order_date" in valid else pd.Series(dtype="datetime64[ns]")
    end = dates.max() if len(dates) else None
    start = end - pd.Timedelta(days=364) if end is not None else None
    period = valid[valid.order_date.between(start, end)] if start is not None else valid.iloc[0:0]
    comparison = period_comparison(valid, start, end) if start is not None else None
    return {"generated_at": generated_at or pd.Timestamp.now(tz="UTC").isoformat(),
      "reporting_start": str(start.date()) if start is not None else None,
      "reporting_end": str(end.date()) if end is not None else None,
      "data_freshness": "Historical snapshot; source dates shown above. This is not a live feed.",
      "kpis": kpis(period), "comparison": comparison,
      "products": group_summary(period,["product_name"]).sort_values("profit") if "product_name" in period else pd.DataFrame(),
      "categories": group_summary(period,["category","sub_category"]) if "category" in period else pd.DataFrame(),
      "regions": group_summary(period,["region"]) if "region" in period else pd.DataFrame(),
      "anomalies": detect_anomalies(valid, quality=quality, previous_quality=previous_quality), "quality": quality,
      "observations": [f"{int((valid.profit < 0).sum()):,} transaction rows have negative recorded profit; negative profit is retained as a valid outcome.",
        "Discount comparisons are observational and do not establish causality."],
      "definitions": ["Management KPI window is the 365 calendar days ending on the latest valid transaction date.","Profit margin = total recorded profit / total sales.","Average order value = total sales / distinct order IDs.","Comparison window is the immediately prior 365 calendar days.","A missing comparison baseline is reported as unavailable."]}

def csv_export(frame): return frame.to_csv(index=False).encode("utf-8-sig")

def excel_export(report):
    comparison=report["comparison"]["metrics"] if report["comparison"] else {}
    sheets={"Report Details":pd.DataFrame([{"frequency":report.get("report_frequency","Management report"),"period_start":report["reporting_start"],"period_end":report["reporting_end"],"data_freshness":report["data_freshness"]}]),"KPI Summary":pd.DataFrame([report["kpis"]]),"Period Comparison":pd.DataFrame([comparison]),"Products":report["products"],"Categories":report["categories"],"Regions":report["regions"],"Anomalies":pd.DataFrame(report["anomalies"]),"Data Quality":pd.DataFrame([report["quality"]])}
    output=BytesIO()
    def cell(value, ref):
        if value is None or (not isinstance(value,(list,dict)) and pd.isna(value)): value=""
        if isinstance(value,(int,float)) and not isinstance(value,bool): return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
    with ZipFile(output,"w",ZIP_DEFLATED) as z:
        names=list(sheets)
        z.writestr("[Content_Types].xml",'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(names)+1))+'</Types>')
        z.writestr("_rels/.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i,n in enumerate(names,1))+'</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(names)+1))+'</Relationships>')
        for i,(name,df) in enumerate(sheets.items(),1):
            data=[list(map(str,df.columns))]+df.astype(object).values.tolist()
            rows=[]
            for ri,row in enumerate(data,1):
                cells=[]
                for ci,value in enumerate(row,1):
                    col=""; n=ci
                    while n: n,rem=divmod(n-1,26); col=chr(65+rem)+col
                    cells.append(cell(value,f"{col}{ri}"))
                rows.append(f'<row r="{ri}">'+''.join(cells)+'</row>')
            z.writestr(f"xl/worksheets/sheet{i}.xml",'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(rows)+'</sheetData></worksheet>')
    return output.getvalue()

def pdf_export(report):
    lines=["RetailIQ Management Report"]
    if report.get("report_frequency"): lines.append(report["report_frequency"])
    lines += [f"Period: {report['reporting_start'] or 'Unavailable'} to {report['reporting_end'] or 'Unavailable'}",f"Generated at: {report['generated_at']}",report["data_freshness"],"", "EXECUTIVE KPIs"]
    lines += [f"{key.title()}: {value:,.2f}" if isinstance(value,(int,float)) and pd.notna(value) else f"{key.title()}: unavailable" for key,value in report["kpis"].items()]
    lines += ["", "PERIOD COMPARISON"]
    if report["comparison"]:
        lines += [f"{key.title()}: absolute {v['absolute_change']:,.2f}; percent {v['percentage_change']:.1%}" if pd.notna(v["percentage_change"]) else f"{key.title()}: baseline unavailable" for key,v in report["comparison"]["metrics"].items()]
    for label,key in (("Top profitable products","products"),("Category performance","categories"),("Regional performance","regions")):
        lines.append(""); lines.append(label.upper())
        data=report[key].sort_values("profit",ascending=False).head(8) if len(report[key]) else report[key]
        lines += [" | ".join(str(row.get(col,"")) for col in list(data.columns)[:5]) for _,row in data.iterrows()]
    lines += ["", "ANOMALIES AND DATA QUALITY"]
    lines += [f"{a['severity'].upper()} {a['metric']} / {a['dimension']} {a['group']}: {a['observed']:,.2f}; baseline {a['baseline']:,.2f}; {a['rule']}" for a in report["anomalies"][:20]]
    q=report["quality"]; lines.append(f"Source rows {q['source_rows']}; valid {q['valid_rows']}; rejected {q['rejected_rows']}; duplicates {q['duplicate_rows']}")
    lines += ["", "DEFINITIONS AND LIMITATIONS"]+report["definitions"]+report["observations"]+["Recorded profit is used as provided; available data does not support causal claims or demand/inventory inference."]
    # Dependency-free multi-page PDF using built-in Helvetica.
    def pdfstr(s):
        s=str(s).encode("cp1252","replace").decode("cp1252").replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
        return s.encode("cp1252").decode("latin1")
    chunks=[lines[i:i+60] for i in range(0,len(lines),60)] or [[]]
    page_ids=[4+2*i for i in range(len(chunks))]
    objects=[b"<< /Type /Catalog /Pages 2 0 R >>",f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] /Count {len(chunks)} >>".encode(),b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i,chunk in enumerate(chunks):
        content="BT /F1 8 Tf 42 754 Td 11 TL "+" ".join(f"({pdfstr(line[:115])}) Tj T*" for line in chunk)+" ET"
        stream=content.encode("latin1"); content_id=page_ids[i]+1
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode())
        objects.append(b"<< /Length "+str(len(stream)).encode()+b" >>\nstream\n"+stream+b"\nendstream")
    output=BytesIO(); output.write(b"%PDF-1.4\n"); offsets=[0]
    for i,obj in enumerate(objects,1): offsets.append(output.tell()); output.write(f"{i} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref=output.tell(); output.write(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]: output.write(f"{off:010d} 00000 n \n".encode())
    output.write(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()); return output.getvalue()

def save_reports(report, directory="reports"):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    paths={"csv":directory/"retailiq_regional_summary.csv","xlsx":directory/"retailiq_management_report.xlsx","pdf":directory/"retailiq_management_report.pdf"}
    paths["csv"].write_bytes(csv_export(report["regions"]))
    paths["xlsx"].write_bytes(excel_export(report)); paths["pdf"].write_bytes(pdf_export(report))
    return paths
