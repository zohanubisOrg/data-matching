import pytest

from scripts.embed_front_v5 import rewrite_drawing, embed_column_x


def test_embed_refuses_to_run_without_validated_release(tmp_path):
    with pytest.raises(ValueError, match="release record and ledger are required"):
        embed_column_x(tmp_path / "source.xlsx", tmp_path / "out.xlsx", {})


def test_drawing_rewrite_fails_if_accepted_row_has_no_x_anchor():
    drawing = b'''<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><xdr:twoCellAnchor><xdr:from><xdr:col>22</xdr:col><xdr:row>0</xdr:row></xdr:from><xdr:pic><xdr:blipFill><a:blip r:embed="rId1"/></xdr:blipFill><xdr:nvPicPr><xdr:cNvPr id="2" name="Picture 2"/></xdr:nvPicPr></xdr:pic></xdr:twoCellAnchor></xdr:wsDr>'''
    with pytest.raises(RuntimeError, match="accepted rows have no X anchor"):
        rewrite_drawing(drawing, {4: b"jpeg"})
