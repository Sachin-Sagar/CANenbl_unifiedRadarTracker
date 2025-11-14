import unittest
import os
import sys
import multiprocessing
import io
import time

class Tee(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

def main():
    """
    Test runner to discover and execute all tests in the 'test_cases' directory.
    Allows the user to select which tests to run.
    Redirects output to a log file and prints a final summary.
    """
    # --- Create a single timestamped output directory for this test run ---
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    run_output_dir = os.path.join(project_root, 'tests', 'output', f"test_run_{timestamp}")
    os.makedirs(run_output_dir, exist_ok=True)
    
    # Set environment variable for other processes to use
    os.environ['TEST_RUN_OUTPUT_DIR'] = run_output_dir
    
    log_file_path = os.path.join(run_output_dir, 'tst_console_out.txt')

    # --- Redirect stdout and stderr ---
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_file_path, 'w')
    
    tee_stdout = Tee(original_stdout, log_file)
    tee_stderr = Tee(original_stderr, log_file)
    
    sys.stdout = tee_stdout
    sys.stderr = tee_stderr

    result = None
    selected_suite = unittest.TestSuite()
    try:
        # Set the start method for all multiprocessing operations
        try:
            multiprocessing.set_start_method('spawn', force=True)
        except RuntimeError:
            pass

        # Add project root to path
        sys.path.insert(0, project_root)
        sys.path.insert(0, os.path.dirname(__file__))

        # Discover all tests
        loader = unittest.TestLoader()
        start_dir = os.path.join(os.path.dirname(__file__), 'test_cases')
        suite = loader.discover(start_dir=start_dir, pattern='test_*.py')
        
        all_tests = []
        def collect_tests_from_suite(suite_or_test):
            if isinstance(suite_or_test, unittest.TestSuite):
                for test in suite_or_test:
                    collect_tests_from_suite(test)
            else:
                all_tests.append(suite_or_test)
        collect_tests_from_suite(suite)

        # --- Use a set to ensure tests are unique and sort them ---
        unique_tests = sorted(list(set(all_tests)), key=lambda x: x.id())

        # --- Present menu to user ---
        print("\n" + "="*70)
        print(" " * 25 + "AVAILABLE TESTS")
        print("="*70)
        for i, test in enumerate(unique_tests):
            print(f"  [{i+1}] {test.__class__.__name__}.{test._testMethodName}")
        print("\n  [all] Run all tests")
        print("="*70)

        # --- Get user choice ---
        choice = input("\nEnter test number(s) to run (e.g., '1,3,5'), or 'all': ")

        # --- Create a new suite based on choice ---
        if choice.lower() == 'all':
            selected_suite = suite
        else:
            try:
                test_indices = [int(x.strip()) - 1 for x in choice.split(',')]
                for test_index in test_indices:
                    if 0 <= test_index < len(unique_tests):
                        selected_suite.addTest(unique_tests[test_index])
                    else:
                        print(f"Warning: Test number {test_index + 1} is out of range and will be ignored.")
            except ValueError:
                print("Error: Invalid input. Please enter numbers separated by commas, or 'all'.")
                sys.exit(1)

        if selected_suite.countTestCases() == 0:
            print("No valid tests selected to run.")
        else:
            # Run the selected tests
            runner = unittest.TextTestRunner(verbosity=1)
            result = runner.run(selected_suite)

    finally:
        # --- Print Final Summary ---
        if result is not None:
            print("\n\n" + "="*70)
            print(" " * 25 + "TEST SUITE SUMMARY")
            print("="*70)
            
            summary_tests = []
            def collect_summary_tests(s):
                if isinstance(s, unittest.TestSuite):
                    for t in s:
                        collect_summary_tests(t)
                else:
                    summary_tests.append(s)
            collect_summary_tests(selected_suite)

            # Filter out None values to prevent errors
            summary_tests = [t for t in summary_tests if t is not None]

            failures = {test.id() for test, _ in result.failures if test}
            errors = {test.id() for test, _ in result.errors if test}
            skipped = {test.id() for test, _ in result.skipped if test}
            
            passed_tests = [t for t in summary_tests if t.id() not in failures and t.id() not in errors and t.id() not in skipped]

            print(f"\nTotal tests run: {result.testsRun}")
            print(f"Passed: {len(passed_tests)}")
            print(f"Failed: {len(failures)}")
            print(f"Errors: {len(errors)}")
            print(f"Skipped: {len(skipped)}")
            
            if passed_tests:
                print("\n--- PASSED ---")
                for test in passed_tests:
                    if test: # Add check for None
                        print(f"  [+] {test.__class__.__name__}.{test._testMethodName}")

            if result.failures:
                print("\n--- FAILED ---")
                for test, traceback_info in result.failures:
                    if test: # Add check for None
                        print(f"  [-] {test.__class__.__name__}.{test._testMethodName}")
            
            if result.errors:
                print("\n--- ERRORS ---")
                for test, traceback_info in result.errors:
                    if test: # Add check for None
                        print(f"  [E] {test.__class__.__name__}.{test._testMethodName}")
            
            if result.skipped:
                print("\n--- SKIPPED ---")
                for test, reason in result.skipped:
                    if test: # Add check for None
                        print(f"  [S] {test.__class__.__name__}.{test._testMethodName}: {reason}")

            print("\n" + "="*70)

        # --- Restore stdout and stderr ---
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()
        
        print(f"\nFull console output saved to: {os.path.abspath(log_file_path)}")

        # Exit with a non-zero status code if any tests failed
        if result and not result.wasSuccessful():
            sys.exit(1)

if __name__ == '__main__':
    main()
