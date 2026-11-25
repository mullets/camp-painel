"""PDF sem perda a partir dos TIFF originais (CAMP-PROJETO, 25/11/2026).

Rafael: "exportar um pdf feito em cima dos tifs em alta qualidade … no máximo possível em cima do tiff original".

Escritor de PDF mínimo, sem biblioteca nova: cada página é UMA imagem, no tamanho em pixels do TIFF (nunca reduzida), com os pixels
guardados em FlateDecode (compressão sem perda, a mesma do PNG). Nada passa por JPEG: o que se vê no PDF são os pixels do TIFF.
- O tamanho da página sai do DPI gravado no TIFF (sem DPI: 300, e a página avisa no resultado). Página maior que o limite do PDF
  (14.400 pt ≈ 5 m) é desenhada em escala menor no papel, mas a imagem continua com todos os pixels.
- Modos: RGB e L (8 bits) como estão; "1" (preto e branco) em 1 bit; I;16 (cinza 16 bits) em 16 bits; CMYK em DeviceCMYK. Paleta (P),
  transparência (RGBA/LA) e outros modos viram RGB 8 bits (o canal de transparência sai; a cor fica igual). Isso é anotado em `notas`.
- Memória: uma imagem por vez; a compressão vai por faixas de linhas direto para o arquivo.
- Capa opcional (texto simples, Helvetica, acentos em WinAnsi).
"""
from __future__ import annotations

import zlib
from pathlib import Path

LIMITE_PT = 14400.0
DPI_PADRAO = 300


def _esc(t: str) -> bytes:
    b = str(t).encode("cp1252", "replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class EscritorPDF:
    """Escreve o PDF objeto a objeto num arquivo aberto (as imagens nunca ficam inteiras na memória do PDF)."""

    def __init__(self, caminho: Path):
        self.f = open(caminho, "wb")
        self.offsets: list[int] = []
        self.paginas: list[int] = []
        self.f.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        self._pages_id = self._reservar()
        self._fonte_id = None

    def _reservar(self) -> int:
        self.offsets.append(0)
        return len(self.offsets)

    def _abrir(self, oid: int) -> None:
        self.offsets[oid - 1] = self.f.tell()
        self.f.write(f"{oid} 0 obj\n".encode())

    def _obj(self, oid: int, corpo: bytes) -> None:
        self._abrir(oid)
        self.f.write(corpo + b"\nendobj\n")

    def _fonte(self) -> int:
        if self._fonte_id is None:
            self._fonte_id = self._reservar()
            self._obj(self._fonte_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        return self._fonte_id

    def _pagina(self, w_pt: float, h_pt: float, conteudo: bytes, recursos: bytes) -> None:
        cid = self._reservar()
        self._obj(cid, b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream")
        pid = self._reservar()
        self._obj(pid, (f"<< /Type /Page /Parent {self._pages_id} 0 R /MediaBox [0 0 {w_pt:.2f} {h_pt:.2f}] ").encode()
                  + b"/Resources " + recursos + f" /Contents {cid} 0 R >>".encode())
        self.paginas.append(pid)

    def capa(self, linhas: list[tuple[int, str]]) -> None:
        """Página A4 com linhas de texto: [(tamanho da fonte, texto)]."""
        fid = self._fonte()
        y, partes = 790.0, [b"BT"]
        for tam, txt in linhas:
            y -= tam * 1.6
            if y < 40:
                break
            partes.append(b"/F1 %d Tf 1 0 0 1 56 %.1f Tm (" % (tam, y) + _esc(txt) + b") Tj")
        partes.append(b"ET")
        self._pagina(595.28, 841.89, b"\n".join(partes), f"<< /Font << /F1 {fid} 0 R >> >>".encode())

    def imagem(self, caminho: Path) -> dict:
        """Uma página com a imagem inteira do arquivo. Devolve {largura, altura, dpi, modo, nota}."""
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None          # pranchas grandes passam de 90 MP: o arquivo é nosso (QNAP), não da internet
        nota = ""
        with Image.open(caminho) as im0:
            im0.load()
            dpi = im0.info.get("dpi") or im0.info.get("resolution")
            try:
                dx, dy = (float(dpi[0]), float(dpi[1])) if dpi else (0.0, 0.0)
            except (TypeError, ValueError, IndexError):
                dx = dy = 0.0
            if dx <= 1 or dy <= 1:
                dx = dy = float(DPI_PADRAO)
                nota = f"sem DPI no arquivo: página calculada a {DPI_PADRAO} dpi"
            modo = im0.mode
            if modo in ("RGB", "L", "1", "CMYK"):
                im = im0
            elif modo in ("I;16", "I;16B", "I;16L"):
                im = im0
            else:
                im = im0.convert("RGB")
                nota = (nota + "; " if nota else "") + f"modo {modo} convertido para RGB 8 bits"
            w, h = im.size
            if im.mode == "RGB":
                cs, bpc, crua = "/DeviceRGB", 8, "RGB"
            elif im.mode == "L":
                cs, bpc, crua = "/DeviceGray", 8, "L"
            elif im.mode == "1":
                cs, bpc, crua = "/DeviceGray", 1, "1"
            elif im.mode == "CMYK":
                cs, bpc, crua = "/DeviceCMYK", 8, "CMYK"
            else:
                cs, bpc, crua = "/DeviceGray", 16, "I;16B"
            xid = self._reservar()
            self._abrir(xid)
            cab = (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace {cs} /BitsPerComponent {bpc} "
                   f"/Filter /FlateDecode /Length {xid + 1} 0 R >>\nstream\n").encode()
            len_id = self._reservar()                   # comprimento escrito depois (objeto indireto)
            assert len_id == xid + 1
            self.f.write(cab)
            inicio = self.f.tell()
            z = zlib.compressobj(6)
            faixa = max(1, 4_000_000 // max(1, w * 4))  # ~4 MB de pixels por vez
            for y0 in range(0, h, faixa):
                pedaco = im.crop((0, y0, w, min(h, y0 + faixa)))
                self.f.write(z.compress(pedaco.tobytes("raw", crua)))
            self.f.write(z.flush())
            n = self.f.tell() - inicio
            self.f.write(b"\nendstream\nendobj\n")
            self._obj(len_id, str(n).encode())
        w_pt, h_pt = w * 72.0 / dx, h * 72.0 / dy
        esc = min(1.0, LIMITE_PT / max(w_pt, h_pt))
        if esc < 1.0:
            w_pt, h_pt = w_pt * esc, h_pt * esc
            nota = (nota + "; " if nota else "") + "página maior que o limite do PDF: desenhada menor no papel, com todos os pixels"
        self._pagina(w_pt, h_pt, f"q {w_pt:.4f} 0 0 {h_pt:.4f} 0 0 cm /Im0 Do Q".encode(), f"<< /XObject << /Im0 {xid} 0 R >> >>".encode())
        return {"largura": w, "altura": h, "dpi": round(dx), "modo": modo, "nota": nota}

    def fechar(self, titulo: str = "") -> int:
        kids = " ".join(f"{p} 0 R" for p in self.paginas)
        self._obj(self._pages_id, f"<< /Type /Pages /Kids [{kids}] /Count {len(self.paginas)} >>".encode())
        info = self._reservar()
        self._obj(info, b"<< /Title (" + _esc(titulo) + b") /Producer (Painel CAMP) >>")
        cat = self._reservar()
        self._obj(cat, f"<< /Type /Catalog /Pages {self._pages_id} 0 R >>".encode())
        xref = self.f.tell()
        self.f.write(f"xref\n0 {len(self.offsets) + 1}\n0000000000 65535 f \n".encode())
        for o in self.offsets:
            self.f.write(f"{o:010d} 00000 n \n".encode())
        self.f.write(f"trailer\n<< /Size {len(self.offsets) + 1} /Root {cat} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        tam = self.f.tell()
        self.f.close()
        return tam

    def abortar(self) -> None:
        try:
            self.f.close()
        except OSError:
            pass
