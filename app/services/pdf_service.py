import os


def pdf_to_word_text(pdf_path: str, output_path: str) -> int:
    """文本模式：pdfplumber 提取文本和表格 → python-docx 生成 Word。返回页数。"""
    import pdfplumber
    from docx import Document

    doc = Document()
    page_count = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_count += 1
            tables = page.extract_tables()

            if tables:
                for table in tables:
                    if not table:
                        continue
                    rows = len(table)
                    cols = max(len(row) for row in table) if table else 0
                    if rows == 0 or cols == 0:
                        continue
                    doc_table = doc.add_table(rows=rows, cols=cols)
                    for i, row in enumerate(table):
                        for j, cell in enumerate(row):
                            if j < cols:
                                doc_table.rows[i].cells[j].text = cell or ""
                    doc.add_paragraph()
            else:
                text = page.extract_text() or ""
                if text.strip():
                    for line in text.split("\n"):
                        if line.strip():
                            doc.add_paragraph(line)
                    doc.add_paragraph()

            if page_count < len(pdf.pages):
                doc.add_page_break()

    doc.save(output_path)
    return page_count


def pdf_to_word_image(pdf_path: str, output_path: str, dpi: int = 200) -> int:
    """图片模式：PDF 每页渲染为图片嵌入 Word。返回页数。"""
    from pdf2image import convert_from_path
    from docx import Document
    from docx.shared import Inches

    doc = Document()
    images = convert_from_path(pdf_path, dpi=dpi)

    for i, img in enumerate(images):
        temp_img = os.path.join(os.path.dirname(output_path), f"page_{i:04d}.png")
        img.save(temp_img, "PNG")
        doc.add_picture(temp_img, width=Inches(6.5))
        if i < len(images) - 1:
            doc.add_page_break()

    doc.save(output_path)

    for i in range(len(images)):
        temp_img = os.path.join(os.path.dirname(output_path), f"page_{i:04d}.png")
        if os.path.exists(temp_img):
            os.unlink(temp_img)

    return len(images)
