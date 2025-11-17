#!/usr/bin/env python3
"""
Markdown to Notion block converter for reMarkable text content.

Converts markdown-like text from reMarkable OCR into appropriate Notion blocks
with proper formatting (headings, lists, checkboxes, etc.).
"""

import re
from typing import List, Dict, Any, Optional


class MarkdownToNotionConverter:
    """Converts markdown-like text to Notion blocks with proper formatting."""
    
    def __init__(self):
        # Regex patterns for markdown elements
        self.heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        self.checkbox_pattern = re.compile(r'^(\s*)-\s*\[([ x])\]\s+(.+)$', re.MULTILINE)
        self.bullet_pattern = re.compile(r'^(\s*)-\s+(.+)$', re.MULTILINE)
        self.numbered_pattern = re.compile(r'^(\s*)\d+\.\s+(.+)$', re.MULTILINE)
        self.bold_pattern = re.compile(r'\*\*(.+?)\*\*')
        self.italic_pattern = re.compile(r'\*(.+?)\*')
    
    def text_to_notion_blocks(self, text: str, max_blocks: int = 100) -> List[Dict[str, Any]]:
        """
        Convert markdown-like text to Notion blocks.
        
        Args:
            text: Raw text content with markdown-like formatting
            max_blocks: Maximum number of blocks to create (to avoid API limits)
            
        Returns:
            List of Notion block dictionaries
        """
        if not text or not text.strip():
            return [{
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": "(No readable text extracted)"}
                    }]
                }
            }]
        
        blocks = []
        lines = text.split('\n')
        current_list_items = []
        current_list_type = None
        
        for line in lines:
            if len(blocks) >= max_blocks:
                # Add truncation notice
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": "... (content truncated to avoid API limits)"},
                            "annotations": {"italic": True, "color": "gray"}
                        }]
                    }
                })
                break
                
            line = line.strip()
            if not line:
                # Flush any pending list items
                if current_list_items:
                    blocks.extend(self._create_list_blocks(current_list_items, current_list_type))
                    current_list_items = []
                    current_list_type = None
                continue
            
            # Check for headings
            if line.startswith('#'):
                # Flush any pending list items first
                if current_list_items:
                    blocks.extend(self._create_list_blocks(current_list_items, current_list_type))
                    current_list_items = []
                    current_list_type = None
                    
                blocks.append(self._create_heading_block(line))
                continue
            
            # Check for horizontal rules
            if line.startswith('---') and len(line.strip('-')) == 0:
                # Flush any pending list items first
                if current_list_items:
                    blocks.extend(self._create_list_blocks(current_list_items, current_list_type))
                    current_list_items = []
                    current_list_type = None
                    
                blocks.append(self._create_divider_block())
                continue
            
            # Check for checkboxes
            checkbox_match = re.match(r'^(\s*)-\s*\[([ xX])\]\s+(.+)$', line)
            if checkbox_match:
                if current_list_type != 'checkbox':
                    # Flush any pending non-checkbox list items
                    if current_list_items:
                        blocks.extend(self._create_list_blocks(current_list_items, current_list_type))
                        current_list_items = []
                    current_list_type = 'checkbox'
                
                indent, checked, content = checkbox_match.groups()
                current_list_items.append({
                    'content': content.strip(),
                    'checked': checked.lower() in ['x'],
                    'indent': len(indent)
                })
                continue
            
            # Check for bullet points (support both - and * for markdown compatibility)
            bullet_match = re.match(r'^(\s*)[-*]\s+(.+)$', line)
            if bullet_match:
                if current_list_type != 'bullet':
                    # Flush any pending non-bullet list items
                    if current_list_items:
                        blocks.extend(self._create_list_blocks(current_list_items, current_list_type))
                        current_list_items = []
                    current_list_type = 'bullet'
                
                indent, content = bullet_match.groups()
                current_list_items.append({
                    'content': content.strip(),
                    'indent': len(indent)
                })
                continue
            
            # Check for numbered lists
            numbered_match = re.match(r'^(\s*)\d+\.\s+(.+)$', line)
            if numbered_match:
                if current_list_type != 'numbered':
                    # Flush any pending non-numbered list items
                    if current_list_items:
                        blocks.extend(self._create_list_blocks(current_list_items, current_list_type))
                        current_list_items = []
                    current_list_type = 'numbered'
                
                indent, content = numbered_match.groups()
                current_list_items.append({
                    'content': content.strip(),
                    'indent': len(indent)
                })
                continue
            
            # Regular paragraph - flush any pending list items first
            if current_list_items:
                blocks.extend(self._create_list_blocks(current_list_items, current_list_type))
                current_list_items = []
                current_list_type = None
                
            blocks.append(self._create_paragraph_block(line))
        
        # Flush any remaining list items
        if current_list_items:
            blocks.extend(self._create_list_blocks(current_list_items, current_list_type))
        
        return blocks[:max_blocks] if blocks else [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "(No content to display)"}
                }]
            }
        }]
    
    def _create_heading_block(self, line: str) -> Dict[str, Any]:
        """Create a Notion heading block from markdown heading."""
        # Count # symbols to determine heading level
        level = 0
        for char in line:
            if char == '#':
                level += 1
            else:
                break
        
        # Notion supports heading_1, heading_2, heading_3
        heading_type = f"heading_{min(level, 3)}"
        content = line[level:].strip()
        
        return {
            "object": "block",
            "type": heading_type,
            heading_type: {
                "rich_text": self._parse_rich_text(content)
            }
        }
    
    def _create_divider_block(self) -> Dict[str, Any]:
        """Create a Notion divider block."""
        return {
            "object": "block",
            "type": "divider",
            "divider": {}
        }
    
    def _create_paragraph_block(self, content: str) -> Dict[str, Any]:
        """Create a Notion paragraph block with rich text formatting."""
        # Limit content length to avoid API limits
        if len(content) > 1500:
            content = content[:1500] + "..."
            
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": self._parse_rich_text(content)
            }
        }
    
    def _create_list_blocks(self, items: List[Dict], list_type: str) -> List[Dict[str, Any]]:
        """Create Notion list blocks from collected list items."""
        blocks = []
        
        for item in items:
            if list_type == 'checkbox':
                block = {
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": self._parse_rich_text(item['content']),
                        "checked": item['checked']
                    }
                }
            elif list_type == 'bullet':
                block = {
                    "object": "block", 
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": self._parse_rich_text(item['content'])
                    }
                }
            elif list_type == 'numbered':
                block = {
                    "object": "block",
                    "type": "numbered_list_item", 
                    "numbered_list_item": {
                        "rich_text": self._parse_rich_text(item['content'])
                    }
                }
            else:
                # Fallback to paragraph
                block = self._create_paragraph_block(item['content'])
            
            blocks.append(block)
        
        return blocks
    
    def _parse_rich_text(self, content: str) -> List[Dict[str, Any]]:
        """Parse text content and create rich text objects with formatting."""
        if not content:
            return [{"type": "text", "text": {"content": ""}}]
        
        # For now, we'll keep it simple and handle basic bold/italic
        # More complex parsing could be added here
        rich_text = []
        
        # Split by bold markers first
        parts = re.split(r'(\*\*.*?\*\*)', content)
        
        for part in parts:
            if not part:
                continue
                
            # Check if this part is bold
            bold_match = re.match(r'\*\*(.+?)\*\*', part)
            if bold_match:
                bold_content = bold_match.group(1)
                rich_text.append({
                    "type": "text",
                    "text": {"content": bold_content},
                    "annotations": {"bold": True}
                })
            else:
                # Handle italic within non-bold text
                italic_parts = re.split(r'(\*.*?\*)', part)
                for italic_part in italic_parts:
                    if not italic_part:
                        continue
                        
                    italic_match = re.match(r'\*(.+?)\*', italic_part)
                    if italic_match and not italic_part.startswith('**'):
                        italic_content = italic_match.group(1)
                        rich_text.append({
                            "type": "text",
                            "text": {"content": italic_content},
                            "annotations": {"italic": True}
                        })
                    else:
                        # Regular text
                        if italic_part:
                            rich_text.append({
                                "type": "text",
                                "text": {"content": italic_part}
                            })
        
        # If no rich text was created, return plain text
        if not rich_text:
            rich_text = [{"type": "text", "text": {"content": content}}]
        
        # Ensure no single rich text item exceeds Notion's limits
        for item in rich_text:
            if len(item["text"]["content"]) > 2000:
                item["text"]["content"] = item["text"]["content"][:1997] + "..."
        
        return rich_text