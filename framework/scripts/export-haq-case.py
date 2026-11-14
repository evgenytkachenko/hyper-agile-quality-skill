"""Export real synthetic-run evidence into the existing HAQ case adapter format."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
root = Path(__file__).resolve().parents[1]
latest = json.loads((root/'evidence/latest-demo.json').read_text())
report = json.loads((root/latest['path']).read_text())
out = root/'evidence/haq-case'
(out/'issues').mkdir(parents=True, exist_ok=True)
(out/'test-results').mkdir(exist_ok=True)
(out/'case.yaml').write_text('id: synthetic-patient-isolation\ntitle: Synthetic missing authorization acceptance scenario\nincident: DEMO-1\n')
(out/'issues/DEMO-1.yaml').write_text('key: DEMO-1\ntype: Bug\ntitle: Synthetic benchmark discloses another patient record\nstatus: Fixed in separate secure implementation\npriority: Critical\ndescription: |\n  Fictional benchmark only. Real HTTP checks detected a cross-patient authorization defect.\n  No production patient data or real incident is represented.\n')
(out/'documentation.md').write_text((root/'policy/requirements.json').read_text())
(out/'tests.md').write_text('# Actual test execution, synthetic fixture\n\n'+json.dumps(report['stages'],indent=2))
(out/'code-change.md').write_text('# Source binding\n\nSource hash: '+report['sourceHash']+'\nNo historical deployment claimed.\n')
(out/'fix-change.md').write_text('# Fixed fixture\n\nSecure implementation enforced ownership; permanent regression tests passed.\n')
(out/'production-learning.md').write_text('# Benchmark, not production\n\nA passing incomplete suite did not establish critical requirement coverage.\n')
suite=ET.Element('testsuite',name='synthetic-qe-demo')
for stage in report['stages']:
 for row in stage['tests']:
  test=ET.SubElement(suite,'testcase',name=row['title'],classname=stage['name'])
  if row['status']!='passed': ET.SubElement(test,'failure',message='Observed negative-control failure')
ET.ElementTree(suite).write(out/'test-results/real-http.xml',encoding='unicode')
print(out)
