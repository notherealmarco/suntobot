#!/usr/bin/env python3
"""
Test script to simulate Telegram's HTML parsing to identify the exact issue.
This will help us understand what specific HTML patterns cause the byte offset error.
"""

import re
import sys
import os

# Add src to path so we can import the function
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from summary_engine import sanitize_html


def simulate_telegram_parse_error(html_text):
    """
    Simulate what might cause Telegram's "unexpected end tag at byte offset" error.
    This error typically happens when:
    1. A closing tag appears without a matching opening tag
    2. Tags are improperly nested
    3. There are encoding issues with special characters
    """
    
    print(f"\nAnalyzing: {repr(html_text)}")
    print(f"Length: {len(html_text)} chars, {len(html_text.encode('utf-8'))} bytes")
    
    # Convert to bytes to check positions
    html_bytes = html_text.encode('utf-8')
    
    # Find all HTML tags and their byte positions
    tag_pattern = r'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>'
    
    tags_info = []
    for match in re.finditer(tag_pattern, html_text):
        is_closing = match.group(1) == '/'
        tag_name = match.group(2).lower()
        full_match = match.group(0)
        
        # Calculate byte positions
        char_start = match.start()
        char_end = match.end()
        
        # Convert character positions to byte positions
        byte_start = len(html_text[:char_start].encode('utf-8'))
        byte_end = len(html_text[:char_end].encode('utf-8'))
        
        tags_info.append({
            'tag': tag_name,
            'is_closing': is_closing,
            'full_match': full_match,
            'char_pos': (char_start, char_end),
            'byte_pos': (byte_start, byte_end),
        })
    
    print("Tags found:")
    for i, tag_info in enumerate(tags_info):
        print(f"  {i+1}. {tag_info['full_match']} - "
              f"Bytes {tag_info['byte_pos'][0]}-{tag_info['byte_pos'][1]} "
              f"({'closing' if tag_info['is_closing'] else 'opening'})")
    
    # Check for potential issues
    issues = []
    
    # Check for orphaned closing tags
    tag_stack = []
    for tag_info in tags_info:
        if tag_info['is_closing']:
            # Look for matching opening tag
            found_match = False
            for j in range(len(tag_stack) - 1, -1, -1):
                if tag_stack[j]['tag'] == tag_info['tag']:
                    # Found match, remove it
                    tag_stack.pop(j)
                    found_match = True
                    break
            
            if not found_match:
                issues.append(f"Orphaned closing tag </{tag_info['tag']}> at byte {tag_info['byte_pos'][0]}")
        else:
            tag_stack.append(tag_info)
    
    # Remaining tags in stack are unclosed
    for tag_info in tag_stack:
        issues.append(f"Unclosed opening tag <{tag_info['tag']}> at byte {tag_info['byte_pos'][0]}")
    
    # Check around byte offset 199 specifically
    if len(html_bytes) > 199:
        context_start = max(0, 190)
        context_end = min(len(html_bytes), 210)
        context = html_bytes[context_start:context_end]
        print(f"\nContext around byte 199: {repr(context)}")
        
        # Check if there's a tag boundary at or near byte 199
        for tag_info in tags_info:
            start, end = tag_info['byte_pos']
            if 195 <= start <= 205 or 195 <= end <= 205:
                print(f"Tag near byte 199: {tag_info['full_match']} at bytes {start}-{end}")
    
    if issues:
        print(f"\nPotential issues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nNo obvious structural issues found.")
    
    return issues


def test_specific_patterns():
    """Test patterns that might specifically cause byte offset 199 error."""
    
    patterns_to_test = [
        # Pattern 1: Text that puts a closing tag exactly at byte 199
        "A" * 195 + "</b>",
        
        # Pattern 2: Text with unicode that might affect byte counting
        "🎉" * 48 + "</b>",  # Each emoji is 4 bytes, so 48*4=192 + 4 for </b> = 196
        
        # Pattern 3: Mixed content with problematic nesting around position 199
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 3 + "<b>Bold</i>",
        
        # Pattern 4: Real-world example - summary text with HTML
        """Here's a <b>summary</b> of the recent chat activity:

🔥 <i>Hot topics discussed:</i>
- Project development updates
- Technical discussions about <code>HTML sanitization</code>
- User questions and bot responses</b>""",
        
        # Pattern 5: Long text with multiple nested tags
        "The conversation covered several important topics. " * 2 + 
        "<b>Key points: <i>development progress</i>, <u>technical challenges</b></u>, and user feedback.",
        
        # Pattern 6: Text with forward slash that might confuse parsing
        "Discussion about file paths like /home/user/project and <b>code examples</b>",
        
        # Pattern 7: Complex nested structure that might break
        "<b>Bold text with <i>italic and <u>underlined</i> content</u> mixed</b>",
        
        # Pattern 8: Text with HTML entities that affect byte counting
        "Text with &amp; entities &lt;script&gt; and <b>bold</b> formatting",
    ]
    
    print("Testing specific patterns that might cause byte offset errors...")
    print("=" * 70)
    
    for i, pattern in enumerate(patterns_to_test, 1):
        print(f"\n{'='*20} Test Pattern {i} {'='*20}")
        
        # Test original pattern
        print("ORIGINAL PATTERN:")
        issues = simulate_telegram_parse_error(pattern)
        
        # Test sanitized version
        print("\nAFTER SANITIZATION:")
        try:
            sanitized = sanitize_html(pattern)
            print(f"Sanitized result: {repr(sanitized)}")
            sanitized_issues = simulate_telegram_parse_error(sanitized)
            
            if sanitized_issues:
                print("⚠️  Sanitization did not fix all issues!")
            else:
                print("✅ Sanitization appears to have fixed the issues.")
                
        except Exception as e:
            print(f"❌ Sanitization failed: {e}")


if __name__ == "__main__":
    print("Telegram HTML Error Simulator")
    print("=" * 70)
    
    test_specific_patterns()
    
    print("\n" + "=" * 70)
    print("Analysis complete!")
    print("\nLookup for patterns that:")
    print("1. Have orphaned closing tags")
    print("2. Have improperly nested tags") 
    print("3. Have issues around specific byte positions")
    print("4. Still have problems after sanitization")
