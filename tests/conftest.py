import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Never let tests write fake logs/reports into the user's real ~/FusionDFM (field reports read those files).
_TMP = tempfile.mkdtemp(prefix="fusiondfm_tests_")
os.environ["FUSIONDFM_LOG_DIR"] = os.path.join(_TMP, "logs")
os.environ["FUSIONDFM_REPORT_DIR"] = os.path.join(_TMP, "reports")
