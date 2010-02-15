"""
Do a Python test on the app.

:Test-Layer: python
"""
import unittest
from bioport.mail_validation import check_email 

class TestEmailValidation(unittest.TestCase):
    def test_email_validation_correct(self):
        self.failUnless(check_email('me@example.com'))
        self.failUnless(check_email('me+can_have-some:special_chars@example.com'))
        self.failUnless(check_email('E.J.vanderVeldt1@uu.nl'))
    def test_email_validation_incorrect(self):
        self.failIf(check_email('meexample.com'))
        self.failIf(check_email('@ll.com'))
