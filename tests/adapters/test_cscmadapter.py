# tests/adapters/test_cscmadapter.py

from openscm.adapters.cscmadapter import CSCMAdapter

from base import _AdapterTester


class TestCSCMAdapter(_AdapterTester):
    tadapter = CSCMAdapter

    # if necessary, you can extend the tests e.g.
    def test_run(self, test_adapter, test_run_parameters):
        super().test_run(cscmadatpter, test_run_parameters)
        # TODO some specific test of your adapter here

    def test_my_special_feature(self, test_adapter):
        pass
        # TODO test some special feature of your adapter class
