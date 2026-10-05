"""Offline regression checks for preserving service data and rejecting conflicts."""
import ast
import hashlib
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / 'unlimited_coop'
tree = ast.parse((source/'__init__.py').read_text())
chosen = [n for n in tree.body if
          (isinstance(n, ast.FunctionDef) and n.name in ('parse_patch', 'register_hotfixes')) or
          (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('HOTFIX','TYPED') for t in n.targets))]
ns = {'re':re}
exec(compile(ast.Module(body=chosen, type_ignores=[]), 'isolated_hotfix_registration', 'exec'), ns)
records = ns['parse_patch']((source/'cooppatch.txt').read_text())


class Service:
    def __init__(self):
        self.ServiceName='Micropatch'
        self.Keys=['OfficialPatch']
        self.Values=['unchanged']
    def _path_name(self): return 'Transient.SparkServiceConfiguration_987'


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.service = Service()
        ns['RECORDS']=records
        ns['unrealsdk']=SimpleNamespace(find_all=lambda _: [self.service])

    def test_enabled_payload_and_idempotence(self):
        self.assertEqual(hashlib.sha256((source/'cooppatch.txt').read_bytes()).hexdigest(),
                         '804f7f740ee2c1d0c5ca6a1e9dec5cbce4c9a6d3c7cf09407ff1c3b56b9712da')
        self.assertEqual(len(records),39)
        self.assertEqual(sum(bool(r['hotfix']) for r in records),13)
        ns['register_hotfixes']()
        first=(self.service.Keys.copy(),self.service.Values.copy())
        ns['register_hotfixes']()
        self.assertEqual(first,(self.service.Keys,self.service.Values))
        self.assertEqual(len(self.service.Keys),14)
        self.assertEqual(self.service.Values[0],'unchanged')
        self.assertEqual(ns['_service_status']['status'],'registered')

    def test_conflict_leaves_service_untouched(self):
        self.service.Keys.append('SparkLevelPatchEntry-COOPPATCH1')
        self.service.Values.append('different payload')
        first=(self.service.Keys.copy(),self.service.Values.copy())
        ns['register_hotfixes']()
        self.assertEqual(first,(self.service.Keys,self.service.Values))
        self.assertEqual(ns['_service_status']['status'],'error')

    def test_missing_or_ambiguous_service(self):
        for services in ([], [self.service,Service()]):
            ns['unrealsdk']=SimpleNamespace(find_all=lambda _:services)
            ns['register_hotfixes']()
            self.assertEqual(ns['_service_status']['status'],'pending')
            self.assertEqual(self.service.Keys,['OfficialPatch'])

    def test_broken_existing_pairs(self):
        self.service.Values=[]
        ns['register_hotfixes']()
        self.assertEqual(ns['_service_status']['status'],'error')
        self.assertEqual(self.service.Values,[])


if __name__=='__main__': unittest.main()
