from pathlib import Path

from tools.rimworld_xml import discover_xml_files


def test_discover_xml_files_skips_unsupported_versioned_mod_refs(tmp_path: Path) -> None:
    root = tmp_path / 'RW refs'
    mod_dir = root / 'MODs Refs' / 'ExampleMod' / '1.4' / 'Defs'
    mod_dir.mkdir(parents=True)
    (mod_dir / 'ThingDefs.xml').write_text('<Defs/>', encoding='utf-8')

    versioned_mod_dir = root / 'MODs Refs' / 'ExampleMod' / '1.6' / 'Defs'
    versioned_mod_dir.mkdir(parents=True)
    (versioned_mod_dir / 'ThingDefs.xml').write_text('<Defs/>', encoding='utf-8')

    discovered = discover_xml_files(root)

    assert discovered == [versioned_mod_dir / 'ThingDefs.xml']


def test_discover_xml_files_keeps_unversioned_reference_trees(tmp_path: Path) -> None:
    root = tmp_path / 'RW refs'
    defs_dir = root / '1.6.9676' / 'XML' / 'Defs'
    defs_dir.mkdir(parents=True)
    xml_path = defs_dir / 'ThingDefs.xml'
    xml_path.write_text('<Defs/>', encoding='utf-8')

    discovered = discover_xml_files(root)

    assert discovered == [xml_path]


def test_discover_xml_files_prefers_default_version_for_versioned_mod_refs(tmp_path: Path) -> None:
    root = tmp_path / 'RW refs'

    for version in ('1.3', '1.4', '1.5', '1.6'):
        version_dir = root / 'MODs Refs' / 'ExampleMod' / version / 'Defs'
        version_dir.mkdir(parents=True)
        (version_dir / 'ThingDefs.xml').write_text('<Defs/>', encoding='utf-8')

    other_mod_default_dir = root / 'MODs Refs' / 'OtherMod' / '1.6' / 'Defs'
    other_mod_default_dir.mkdir(parents=True)
    other_mod_xml = other_mod_default_dir / 'ThingDefs.xml'
    other_mod_xml.write_text('<Defs/>', encoding='utf-8')

    legacy_mod_dir = root / 'MODs Refs' / 'LegacyMod' / '1.4' / 'Defs'
    legacy_mod_dir.mkdir(parents=True)
    legacy_xml = legacy_mod_dir / 'ThingDefs.xml'
    legacy_xml.write_text('<Defs/>', encoding='utf-8')

    discovered = discover_xml_files(root)

    assert sorted(discovered) == sorted([
        root / 'MODs Refs' / 'ExampleMod' / '1.6' / 'Defs' / 'ThingDefs.xml',
        other_mod_xml,
        legacy_xml,
    ])
