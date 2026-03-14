import os
import sys

# Add src to python path for importing utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from utils import smart_file_search


def test_smart_file_search_empty_cache():
    cache = []
    assert smart_file_search(cache, "query") == []


def test_smart_file_search_empty_query():
    cache = ["file1.txt", "file2.txt"]
    assert smart_file_search(cache, "") == cache
    assert smart_file_search(cache, None) == cache


def test_smart_file_search_exact_basename():
    cache = ["src/app.py", "tests/test_app.py", "app.py"]
    results = smart_file_search(cache, "app.py")
    # Exact basename scores 100, both app.py and src/app.py have basename app.py
    # app.py is shorter than src/app.py, so app.py comes first.
    # tests/test_app.py matches 'app.py' as a substring, so it comes last with score 50.
    assert results == ["app.py", "src/app.py", "tests/test_app.py"]


def test_smart_file_search_exact_path():
    cache = ["src/app.py", "app.py", "src/other.py"]
    results = smart_file_search(cache, "src/app.py")
    # "src/app.py" matches lower_path exactly (score 90)
    assert results == ["src/app.py"]


def test_smart_file_search_basename_prefix():
    cache = ["src/app_config.py", "src/app.py", "app_test.py"]
    results = smart_file_search(cache, "app")
    # app.py -> basename prefix (80)
    # app_test.py -> basename prefix (80)
    # app_config.py -> basename prefix (80)
    # Ordering: score(-80), length, alphabetical
    # len("src/app.py") = 10
    # len("app_test.py") = 11
    # len("src/app_config.py") = 17
    assert results[0] == "src/app.py"
    assert results[1] == "app_test.py"
    assert results[2] == "src/app_config.py"


def test_smart_file_search_basename_substring():
    cache = ["src/my_app.py", "my_app.py", "other.py"]
    results = smart_file_search(cache, "app")
    assert results == ["my_app.py", "src/my_app.py"]


def test_smart_file_search_path_prefix():
    cache = ["src/main.py", "tests/src_test.py"]
    results = smart_file_search(cache, "src/")
    assert results == ["src/main.py"]


def test_smart_file_search_path_substring():
    cache = ["lib/src/main.py", "main.py"]
    results = smart_file_search(cache, "src")
    assert results == ["lib/src/main.py"]


def test_smart_file_search_fuzzy():
    cache = ["src/my_awesome_app.py", "src/other.py"]
    results = smart_file_search(cache, "smapp")
    # 's'rc/'m'y_awesome_'app'.py -> matches subsequence
    assert results == ["src/my_awesome_app.py"]


def test_smart_file_search_case_insensitive():
    cache = ["SRC/App.Py", "tests/TEST_APP.PY"]
    results = smart_file_search(cache, "app.py")
    assert results == ["SRC/App.Py", "tests/TEST_APP.PY"]


def test_smart_file_search_sorting():
    cache = [
        "a/b/c/d/e/app.py",  # exact basename, very long (100)
        "app.py",  # exact basename, shortest (100)
        "src/app.py",  # exact basename, medium (100)
        "src/app_test.py",  # basename prefix (80)
        "my_app.py",  # basename substring (50)
        "myapp.py",  # basename substring (50) shorter
        "src/main.py",  # path prefix for "src", but query is "app.py", wait we use "app" here
    ]

    results = smart_file_search(cache, "app")
    # Scores for "app":
    # a/b/c/d/e/app.py: basename "app.py" -> basename prefix (80)
    # app.py: basename "app.py" -> basename prefix (80)
    # src/app.py: basename "app.py" -> basename prefix (80)
    # src/app_test.py: basename "app_test.py" -> basename prefix (80)
    # my_app.py: basename "my_app.py" -> basename substring (50)
    # myapp.py: basename "myapp.py" -> basename substring (50)
    # src/main.py: -> no match

    # Let's adjust expected order:
    expected = [
        "app.py",  # 80, len=6
        "src/app.py",  # 80, len=10
        "src/app_test.py",  # 80, len=15
        "a/b/c/d/e/app.py",  # 80, len=16
        "myapp.py",  # 50, len=8
        "my_app.py",  # 50, len=9
    ]
    assert results == expected


def test_smart_file_search_fuzzy_ordering():
    cache = ["abcd.txt", "a_b_c_d.txt", "a1b2c3d4.txt"]
    results = smart_file_search(cache, "abcd")
    # abcd.txt -> exact basename prefix (80)
    # a_b_c_d.txt -> fuzzy (10)
    # a1b2c3d4.txt -> fuzzy (10)
    # Order for fuzzy: len("a_b_c_d.txt")=11, len("a1b2c3d4.txt")=12
    assert results == ["abcd.txt", "a_b_c_d.txt", "a1b2c3d4.txt"]
