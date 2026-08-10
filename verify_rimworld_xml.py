from pathlib import Path
import tempfile
from tools.rimworld_xml import discover_xml_files

root = Path(tempfile.mkdtemp(dir='.', prefix='rwtest_')) / 'RW refs'
mod_dir = root / 'MODs Refs' / 'ExampleMod' / '1.4' / 'Defs'
mod_dir.mkdir(parents=True)
(mod_dir / 'ThingDefs.xml').write_text('<Defs/>', encoding='utf-8')
versioned_mod_dir = root / 'MODs Refs' / 'ExampleMod' / '1.6' / 'Defs'
versioned_mod_dir.mkdir(parents=True)
(versioned_mod_dir / 'ThingDefs.xml').write_text('<Defs/>', encoding='utf-8')

result = discover_xml_files(root)
print('RESULT', result)
print('EXPECTED', [versioned_mod_dir / 'ThingDefs.xml'])
print('MATCH', result == [versioned_mod_dir / 'ThingDefs.xml'])
