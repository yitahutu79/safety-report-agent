import io
import json
from pathlib import Path
import zipfile

import pytest

from safety_report.pipeline import generate
from safety_report.report_types import REPORT_TYPES, report_profile
from safety_report.word import write_docx


@pytest.mark.parametrize('kind', ['pre_evaluation', 'acceptance_evaluation', 'emergency_plan', 'worktrade_conditions', 'worktrade_current_evaluation', 'safety_standardization', 'dual_prevention'])
def test_each_new_type_has_own_preliminary_template_and_docx_title(kind, tmp_path):
    facility = json.loads((Path(__file__).resolve().parent.parent / 'reference/profile.json').read_text(encoding='utf-8'))
    profile = report_profile(kind, facility)
    report = generate(profile, {'chunks': []}, [], False, chapter_ids=['1'])
    assert report['report_name'] == REPORT_TYPES[kind]['name']
    assert report['structure_confirmed'] is False
    assert report['sections'][0]['title'] == profile['headings'][0]['text']
    assert report['sections'][1]['generation_status'] == 'not_generated'
    output = tmp_path / 'report.docx'
    write_docx(report, profile, output)
    with zipfile.ZipFile(io.BytesIO(output.read_bytes())) as archive:
        document = archive.read('word/document.xml').decode()
    assert REPORT_TYPES[kind]['name'] in document
    assert '待双方确认的试用章节结构' in document


def test_unknown_report_type_is_rejected():
    with pytest.raises(ValueError, match='报告类型无效'):
        report_profile('unknown', {})
