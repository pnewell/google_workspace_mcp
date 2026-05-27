from gdocs.list_span_compiler import (
    BulletOp,
    ListParagraph,
    ListSpanCompiler,
    compile_atomic_rebuild,
    merge_depths,
    resolve_list_span,
    virtualize_after_rebuild,
)


def _para(start: int, end: int, text: str, list_id=None, nest=None) -> ListParagraph:
    return ListParagraph(start, end, text, list_id, nest)


def test_resolve_list_span_expands_adjacent_list():
    paras = [
        _para(5, 17, "Line one\n", "listA", 0),
        _para(17, 31, "Line two\n", "listA", 0),
        _para(31, 47, "Line three\n"),
    ]
    op = BulletOp(31, 47, 1)
    span = resolve_list_span(paras, op)
    assert [p.start for p in span] == [5, 17, 31]


def test_merge_depths_last_op_wins_in_range():
    span = [
        _para(5, 17, "Line one\n", "listA", 0),
        _para(17, 31, "Line two\n", "listA", 0),
        _para(31, 47, "Line three\n", "listA", 1),
    ]
    prior = {5: 0, 17: 0, 31: 1}
    op = BulletOp(17, 31, 1)
    assert merge_depths(span, op, prior) == [0, 1, 1]


def test_compile_atomic_rebuild_sequence():
    span = [
        _para(5, 17, "Line one\n"),
        _para(17, 31, "Line two\n"),
        _para(31, 47, "\tLine three\n"),
    ]
    depths = [0, 0, 1]
    reqs = compile_atomic_rebuild(span, depths, "BULLET_DISC_CIRCLE_SQUARE")
    types = [next(iter(r)) for r in reqs]
    assert "deleteParagraphBullets" not in types
    assert types[0] == "deleteContentRange"
    assert types[-1] == "createParagraphBullets"
    create = reqs[-1]["createParagraphBullets"]
    assert create["range"]["startIndex"] == 5
    assert create["range"]["endIndex"] == 47


def test_compile_atomic_rebuild_mixed_span_deletes_listed_only():
    span = [
        _para(5, 17, "Line one\n", "listA", 0),
        _para(17, 31, "Line two\n", "listA", 0),
        _para(31, 47, "Line three\n"),
    ]
    depths = [0, 0, 1]
    reqs = compile_atomic_rebuild(span, depths, "BULLET_DISC_CIRCLE_SQUARE")
    deletes = [
        r["deleteParagraphBullets"]["range"]
        for r in reqs
        if "deleteParagraphBullets" in r
    ]
    assert deletes == [{"startIndex": 5, "endIndex": 31}]
    assert reqs[-1]["createParagraphBullets"]["range"]["endIndex"] == 48


def test_compile_atomic_rebuild_all_listed_deletes_full_span():
    span = [
        _para(5, 17, "Line one\n", "listA", 0),
        _para(17, 31, "Line two\n", "listA", 0),
        _para(31, 47, "Line three\n", "listA", 0),
    ]
    depths = [0, 0, 1]
    reqs = compile_atomic_rebuild(span, depths, "BULLET_DISC_CIRCLE_SQUARE")
    deletes = [
        r["deleteParagraphBullets"]["range"]
        for r in reqs
        if "deleteParagraphBullets" in r
    ]
    assert deletes == [{"startIndex": 5, "endIndex": 47}]


def test_compiler_virtualizes_for_second_op_in_batch():
    paras = [
        _para(5, 17, "Line one\n"),
        _para(17, 31, "Line two\n"),
        _para(31, 47, "Line three\n"),
    ]
    compiler = ListSpanCompiler()
    req1, virt, span1, depths1 = compiler.apply_op(paras, 5, 31, 0, "UNORDERED")
    assert len(req1) == 1
    assert "createParagraphBullets" in req1[0]
    assert all(p.list_id for p in virt[:2])
    assert virt[2].list_id is None

    req2, virt2, span2, depths2 = compiler.apply_op(virt, 31, 47, 1, "UNORDERED")
    assert [p.start for p in span2] == [5, 17, 31]
    assert depths2 == [0, 0, 1]
    assert len(req2) >= 3

    final = virtualize_after_rebuild(virt, span2, depths2)
    assert final[2].nesting_level == 1
