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

    def test_openscm_standard_parameters_handling(self):
        """
        Test how the adapter handles OpenSCM's standard parameters.

        Implementers must implement this method to check what the user would get when
        OpenSCM's standard parameters are passed to the adapter. It might be that they
        get used, that they are re-mapped to a different name, that they are not
        supported and hence nothing is done. All these behaviours are valid, they just
        need to be tested and validated.

        We give an example of how such a test might look below.
        """
        pass  # TODO: implement once parameter usage can be checked

