#!/usr/bin/env python3
"""
Test script to debug HTML sanitization issues.
This will help identify problems with the sanitize_html function.
"""

import re
import sys
import os

# Add src to path so we can import the function
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from summary_engine import sanitize_html


def test_sanitize_html():
    """Test the sanitize_html function with various inputs."""
    
    test_cases = [
        # Basic cases
        ("Hello world", "Hello world"),
        ("<b>Bold text</b>", "<b>Bold text</b>"),
        ("<i>Italic text</i>", "<i>Italic text</i>"),
        
        # Malformed cases that might cause issues
        ("<b>Unclosed bold", "<b>Unclosed bold"),
        ("Unopened bold</b>", "Unopened bold"),
        ("<b><i>Nested</b></i>", "<b><i>Nested</i></b>"),  # This might be problematic
        
        # Complex nesting
        ("<b>Bold <i>and italic</i> text</b>", "<b>Bold <i>and italic</i> text</b>"),
        
        # Invalid tags
        ("<script>alert('xss')</script>", "alert('xss')"),
        ("<div>Not allowed</div>", "Not allowed"),
        
        # Links
        ('<a href="https://example.com">Link</a>', '<a href="https://example.com">Link</a>'),
        ('<a href="javascript:alert()">Bad link</a>', 'Bad link'),
        
        # Mixed content
        ("Some <b>bold</b> and <i>italic</i> text", "Some <b>bold</b> and <i>italic</i> text"),
        
        # Edge cases that might cause byte offset issues
        ("Text with <b>bold</b> and <unknown>tag</unknown>", "Text with <b>bold</b> and tag"),
        
        # Cases with attributes
        ('<b class="test">Bold</b>', '<b>Bold</b>'),
        
        # Self-closing and br tags
        ("Line 1<br>Line 2", "Line 1\nLine 2"),
        ("Line 1<br />Line 2", "Line 1\nLine 2"),
        
        # HTML entities
        ("&lt;script&gt;", "<script>"),
        ("A &amp; B", "A & B"),
        
        # Empty and None cases
        ("", ""),
        (None, None),
        
        # Problematic cases that might cause the specific error
        ("<b>Text with <i>nested</i> and unclosed", "<b>Text with <i>nested</i> and unclosed"),
        ("Text</b> with orphaned closing", "Text with orphaned closing"),
        ("<b>Bold <i>italic</b> wrong nesting</i>", ""),  # This might be the issue
        
        # Real-world examples that might appear in chat
        ("Check out this <b>awesome</b> project at <a href=\"https://github.com/user/repo\">GitHub</a>!",
         "Check out this <b>awesome</b> project at <a href=\"https://github.com/user/repo\">GitHub</a>!"),
        
        # Deeply nested or complex structures
        ("<b><i><u>Multiple nesting</u></i></b>", "<b><i><u>Multiple nesting</u></i></b>"),
        
        # Cases with special characters that might affect byte counting
        ("Emoji 🚀 with <b>bold</b> text", "Emoji 🚀 with <b>bold</b> text"),
        ("Unicode: café with <i>italic</i>", "Unicode: café with <i>italic</i>"),
    ]
    
    print("Testing HTML sanitization function...")
    print("=" * 60)
    
    failed_cases = []
    
    for i, (input_text, expected) in enumerate(test_cases, 1):
        try:
            result = sanitize_html(input_text)
            
            print(f"\nTest {i}:")
            print(f"Input:    {repr(input_text)}")
            print(f"Expected: {repr(expected)}")
            print(f"Got:      {repr(result)}")
            
            if result != expected:
                print("❌ MISMATCH!")
                failed_cases.append((i, input_text, expected, result))
            else:
                print("✅ PASS")
                
        except Exception as e:
            print(f"\nTest {i}:")
            print(f"Input:    {repr(input_text)}")
            print(f"❌ ERROR: {e}")
            failed_cases.append((i, input_text, expected, f"ERROR: {e}"))
    
    print("\n" + "=" * 60)
    print(f"Tests completed. {len(failed_cases)} failures out of {len(test_cases)} tests.")
    
    if failed_cases:
        print("\nFailed cases:")
        for test_num, input_text, expected, result in failed_cases:
            print(f"  Test {test_num}: {repr(input_text)} -> Expected: {repr(expected)}, Got: {repr(result)}")
    
    return failed_cases


def test_problematic_patterns():
    """Test specific patterns that might cause the 'unexpected end tag' error."""
    
    print("\n" + "=" * 60)
    print("Testing potentially problematic patterns...")
    print("=" * 60)
    
    # These are patterns that commonly cause parsing issues
    problematic_inputs = [
        # Improper nesting (common cause of parsing errors)
        "<b>Bold <i>italic</b> wrong</i>",
        "<i>Italic <b>bold</i> wrong</b>",
        
        # Multiple unclosed tags
        "<b><i><u>Multiple unclosed",
        
        # Mixed valid and invalid nesting
        "<b>Valid <unknown>invalid</unknown> text</b>",
        
        # Tags at specific byte positions that might cause offset issues
        "123456789012345678901234567890<b>Text at position 30</b>",
        
        # Unicode that might affect byte counting
        "🎉🚀✨ Unicode with <b>tags</b> at specific positions",
        
        # Malformed attributes
        '<a href="incomplete',
        '<a href=>Empty</a>',
        '<a href="http://example.com">Link</a> and <b>bold',
        
        # Multiple consecutive tags
        "</b></i></u>Multiple closing tags",
        "<b><i><u>Multiple opening tags",
        
        # Edge case: tag at exact position that might cause byte offset 199 error
        "A" * 190 + "<b>tag</b>",  # Text + tag around position 190-199
        "B" * 195 + "</b>",        # Closing tag around position 195-199
    ]
    
    for i, input_text in enumerate(problematic_inputs, 1):
        try:
            print(f"\nProblematic test {i}:")
            print(f"Input: {repr(input_text)}")
            print(f"Length: {len(input_text)} chars, {len(input_text.encode('utf-8'))} bytes")
            
            result = sanitize_html(input_text)
            print(f"Result: {repr(result)}")
            print("✅ No error")
            
        except Exception as e:
            print(f"❌ ERROR: {e}")
            print(f"Error type: {type(e).__name__}")
            
            # Try to identify the exact position where the error occurs
            if "byte offset" in str(e):
                try:
                    # Extract byte offset from error message
                    import re
                    offset_match = re.search(r'byte offset (\d+)', str(e))
                    if offset_match:
                        offset = int(offset_match.group(1))
                        print(f"Error at byte offset: {offset}")
                        
                        # Show context around the error position
                        bytes_data = input_text.encode('utf-8')
                        if offset < len(bytes_data):
                            start = max(0, offset - 10)
                            end = min(len(bytes_data), offset + 10)
                            context = bytes_data[start:end]
                            print(f"Context around error: {repr(context)}")
                            print(f"Character at offset: {repr(chr(bytes_data[offset]) if offset < len(bytes_data) else 'EOF')}")
                except Exception as parse_error:
                    print(f"Could not parse error details: {parse_error}")


if __name__ == "__main__":
    print("HTML Sanitizer Debug Tool")
    print("=" * 60)
    
    # Run basic tests
    failed_cases = test_sanitize_html()
    
    # Run problematic pattern tests
    test_problematic_patterns()
    
    print("\n" + "=" * 60)
    print("Debug session complete!")
    
    if failed_cases:
        print(f"\n⚠️  Found {len(failed_cases)} issues that need attention.")
    else:
        print("\n✅ All basic tests passed, but check problematic patterns above.")
