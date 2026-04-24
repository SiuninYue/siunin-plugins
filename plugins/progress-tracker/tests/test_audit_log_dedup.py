"""测试两阶段 audit.log 去重。
Pass 1: id 去重（id 相同+内容相同→删副本；id 相同+内容不同→重编号保留两者）
Pass 2: (timestamp+event_type+feature_id) 语义去重
"""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log


def r(id_, ts="2026-04-24T12:00:00Z", et="feature_completed", fid=9, **kw):
    rec = {"id": id_, "tx_id": f"TX-{id_}", "timestamp": ts,
           "event_type": et, "feature_id": fid}
    rec.update(kw)
    return rec


class TestPass1IdDedup:
    def test_exact_duplicate_removed(self):
        rec = r("AUDIT-001")
        result = audit_log.deduplicate_audit_log([rec, dict(rec)])
        assert len(result["kept"]) == 1
        assert len(result["removed"]) == 1
        assert result["id_conflicts"] == 0

    def test_id_collision_renumbered_both_kept(self):
        """同 id 但内容不同 → 两条都保留，冲突条被重编号。"""
        r1 = r("AUDIT-001", fid=1)
        r2 = r("AUDIT-001", fid=2)
        result = audit_log.deduplicate_audit_log([r1, r2])
        assert len(result["kept"]) == 2
        ids = {e["id"] for e in result["kept"]}
        assert len(ids) == 2          # 重编号后两个 id 不同
        assert result["id_conflicts"] == 1

    def test_renumbered_record_has_no_leaked_internal_fields(self):
        """重编号后的记录不应注入 _id_conflict_original 等内部字段到数据本身。"""
        r1 = r("AUDIT-001", fid=1)
        r2 = r("AUDIT-001", fid=2)
        result = audit_log.deduplicate_audit_log([r1, r2])
        for rec in result["kept"]:
            assert "_id_conflict_original" not in rec

    def test_id_conflict_metadata_recorded(self):
        """冲突信息应记录在 metadata 字段，供调用者使用。"""
        r1 = r("AUDIT-001", fid=1)
        r2 = r("AUDIT-001", fid=2)
        result = audit_log.deduplicate_audit_log([r1, r2])
        assert len(result["id_conflict_metadata"]) == 1
        meta = result["id_conflict_metadata"][0]
        assert "original_id" in meta
        assert "new_id" in meta

    def test_no_duplicates_unchanged(self):
        recs = [r("AUDIT-001", ts="T1"), r("AUDIT-002", ts="T2")]
        result = audit_log.deduplicate_audit_log(recs)
        assert len(result["kept"]) == 2
        assert result["removed"] == []
        assert result["id_conflicts"] == 0

    def test_nonstandard_id_format_warns_not_crashes(self):
        """非 AUDIT-XXX 格式的 id 不应导致崩溃，应被处理（最大编号不更新）。"""
        recs = [{"id": "CUSTOM-ID", "tx_id": "TX-1",
                 "timestamp": "2026-04-24T12:00:00Z", "event_type": "schema_migration"}]
        result = audit_log.deduplicate_audit_log(recs)
        assert len(result["kept"]) == 1  # 不崩溃，原样保留


class TestPass2SemanticDedup:
    def test_semantic_duplicate_removed(self):
        """相同 (timestamp+event_type+feature_id) 但不同 id → 语义重复，删副本。"""
        ts = "2026-04-24T12:00:00Z"
        result = audit_log.deduplicate_audit_log([
            r("AUDIT-001", ts=ts, fid=9),
            r("AUDIT-002", ts=ts, fid=9),
        ])
        assert len(result["kept"]) == 1
        assert len(result["semantic_duplicates_removed"]) == 1

    def test_global_event_dedup_without_feature_id(self):
        """feature_id 为 None 的全局事件按 (timestamp+event_type) 去重。"""
        ts = "2026-04-24T12:00:00Z"
        g1 = {"id": "AUDIT-001", "tx_id": "TX-1", "timestamp": ts,
              "event_type": "tracker_reset"}
        g2 = {"id": "AUDIT-002", "tx_id": "TX-2", "timestamp": ts,
              "event_type": "tracker_reset"}
        result = audit_log.deduplicate_audit_log([g1, g2])
        assert len(result["kept"]) == 1

    def test_different_features_not_deduped(self):
        """相同 timestamp+event_type 但不同 feature_id → 不是重复。"""
        ts = "2026-04-24T12:00:00Z"
        result = audit_log.deduplicate_audit_log([
            r("AUDIT-001", ts=ts, fid=1),
            r("AUDIT-002", ts=ts, fid=2),
        ])
        assert len(result["kept"]) == 2