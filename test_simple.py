#!/usr/bin/env python3
"""Simple test to confirm the HTML entity issue."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from summary_engine import sanitize_html

# Test the problematic case
test_input = 'Text with &amp; entities &lt;script&gt; and <b>bold</b> formatting'
print(f"Input: {repr(test_input)}")

result = sanitize_html(test_input)
print(f"Output: {repr(result)}")

# This will contain <script> which is an unclosed tag and will cause Telegram to fail!
print(f"\nProblem: The output contains '<script>' which is an unclosed HTML tag!")
print("This is exactly what would cause 'unexpected end tag' errors in Telegram.")
