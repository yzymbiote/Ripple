"""OpenDART / EDINET collectors, tested with fake API responses (no network, no keys)."""
import datetime as dt
import io
import json
import zipfile

from ripple import config
from ripple.collectors import edinet, opendart
from ripple.sections import cut


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()


class FakeResp:
    def __init__(self, content=b"", data=None):
        self.content, self._data = content, data

    def json(self):
        return self._data


def test_switched_off_without_keys(conn, monkeypatch):
    monkeypatch.setattr(config, "OPENDART_API_KEY", None)
    monkeypatch.setattr(config, "EDINET_API_KEY", None)
    assert "switched_off" in opendart.collect(conn)
    assert "switched_off" in edinet.collect(conn)


def test_opendart_collect(conn, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OPENDART_API_KEY", "dummy")
    monkeypatch.setattr(config, "OPENDART_ENABLED", True)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    corp_xml = ("<result><list><corp_code>00164779</corp_code><corp_name>SK하이닉스</corp_name>"
                "<stock_code>000660</stock_code></list></result>").encode("utf-8")
    report = "<html><body><p>II. 사업의 내용</p><p>주요 고객은 해외 업체로 매출 비중은 40% 입니다.</p><p>III. 재무에 관한 사항</p></body></html>"

    def fake_get(self, url, params=None, **kw):
        if url.endswith("corpCode.xml"):
            return FakeResp(_zip({"CORPCODE.xml": corp_xml}))
        if url.endswith("list.json"):
            if params["corp_code"] != "00164779":
                return FakeResp(data={"status": "013"})
            if params["pblntf_ty"] == "A":
                return FakeResp(data={"status": "000", "total_page": 1, "list": [
                    {"rcept_no": "20260315000001", "report_nm": "사업보고서 (2025.12)", "rcept_dt": "20260315"}]})
            return FakeResp(data={"status": "013"})
        if url.endswith("document.xml"):
            return FakeResp(_zip({"20260315000001.xml": report.encode("utf-8")}))
        raise AssertionError(url)

    monkeypatch.setattr(opendart.PoliteSession, "get", fake_get)
    summary = opendart.collect(conn, log=lambda *_: None)
    assert summary["new_documents"] == 1
    doc = conn.execute("SELECT * FROM documents WHERE source='opendart'").fetchone()
    assert doc["company_id"] == "sk_hynix" and doc["doc_type"] == "annual_report_kr" and doc["published_at"] == "2026-03-15"
    sections = cut(doc["text"], doc["doc_type"])
    assert "사업의 내용" in sections["item_1"] and "40%" in sections["customer_concentration"]
    assert opendart.collect(conn, log=lambda *_: None)["new_documents"] == 0  # never stored twice


def test_edinet_collect(conn, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "EDINET_API_KEY", "dummy")
    monkeypatch.setattr(config, "EDINET_ENABLED", True)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    monkeypatch.setattr(edinet, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(edinet, "FIRST_LOOKBACK_DAYS", 2)
    html = "<html><body><p>事業等のリスク</p><p>主要な販売先への売上割合は30%です。</p><p>経営者による分析</p></body></html>"

    def fake_get(self, url, params=None, **kw):
        if url.endswith("documents.json"):
            results = [{"docID": "S100ABCD", "secCode": "40620", "docTypeCode": "120", "withdrawalStatus": "0",
                        "submitDateTime": params["date"] + " 15:00", "docDescription": "有価証券報告書"},
                       {"docID": "S100ZZZZ", "secCode": "99990", "docTypeCode": "120"}] if params["date"] == "2026-06-20" else []
            return FakeResp(data={"metadata": {"status": "200"}, "results": results})
        return FakeResp(_zip({"XBRL/PublicDoc/0101010_honbun.htm": html.encode("utf-8")}))

    monkeypatch.setattr(edinet.PoliteSession, "get", fake_get)
    summary = edinet.collect(conn, log=lambda *_: None, today=dt.date(2026, 6, 21))
    assert summary["new_documents"] == 1 and summary["days_scanned"] == 3
    doc = conn.execute("SELECT * FROM documents WHERE source='edinet'").fetchone()
    assert doc["company_id"] == "ibiden" and doc["doc_type"] == "annual_report_jp"
    assert "30%" in cut(doc["text"], doc["doc_type"])["item_1a"]
    assert json.loads((tmp_path / "state.json").read_text())["last_day"] == "2026-06-21"
