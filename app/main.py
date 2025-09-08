
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from .services import pdf_analyzer, xlsx_to_html, html_builder

app = FastAPI(title="AI Layout→HTML Agent")

# Allow requests from your Angular frontend
origins = [
    "http://localhost:56878",  # Angular dev server
    # "https://your-production-domain.com"  # optional for prod
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # allow these origins
    allow_credentials=True,
    allow_methods=["*"],         # allow all HTTP methods
    allow_headers=["*"],         # allow all headers
)

class AnalyzeResponse(BaseModel):
    html: str
    css: str
    assets: List[dict] = []
    warnings: List[str] = []

@app.post("/analyze/pdf", response_model=AnalyzeResponse)
async def analyze_pdf(file: UploadFile = File(...), mode: str = "absolute"):
    data = await file.read()
    layout = pdf_analyzer.extract_layout(data)
    html, css, warnings, assets = html_builder.build_from_pdf_layout(layout, mode=mode)

    full_html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document</title>
    <style>
    {css}
    </style>
    </head>
    <body>
    {html}
    </body>
    </html>
    """
    return JSONResponse(content={
        "full_html":full_html,
        "html": html,
        "css": css,
        "assets": assets,
        "warnings": warnings
    })

@app.post("/analyze/xlsx", response_model=AnalyzeResponse)
async def analyze_xlsx(file: UploadFile = File(...)):
    data = await file.read()
    html, css, warnings, assets = xlsx_to_html.convert_xlsx_to_html(data)
    return JSONResponse(content={
        "html": html,
        "css": css,
        "assets": assets,
        "warnings": warnings
    })
