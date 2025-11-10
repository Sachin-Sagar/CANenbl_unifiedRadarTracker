import unittest
import os
import sys

def main():
    """
    Test runner to discover and execute all tests in the 'test_cases' directory.
    """
    # Add project root to path to allow for imports like 'src.can_service'
    # and to allow test cases to find the 'lib' directory.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, project_root)
    
    # Add the tests directory itself to the path to help with module resolution
    sys.path.insert(0, os.path.dirname(__file__))


    # Discover and run tests
    loader = unittest.TestLoader()
    start_dir = os.path.join(os.path.dirname(__file__), 'test_cases')
    
    print(f"Discovering tests in: {start_dir}")
    
    suite = loader.discover(start_dir=start_dir, pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Exit with a non-zero status code if any tests failed
    if not result.wasSuccessful():
        sys.exit(1)

if __name__ == '__main__':
    main()
