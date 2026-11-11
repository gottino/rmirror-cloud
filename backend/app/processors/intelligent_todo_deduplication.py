#!/usr/bin/env python3
"""
Intelligent Todo Deduplication for OCR Variations

This module provides smart deduplication logic to handle OCR inconsistencies
that create similar but slightly different todo text variations.

Key features:
1. Fuzzy string matching to detect similar todos
2. One-to-one matching of new todos to stored ones; stored todos left unmatched are reported
3. Positional awareness using bounding box proximity
4. Smart similarity scoring with customizable thresholds
"""

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TodoCandidate:
    """Represents a todo candidate with metadata for deduplication."""

    text: str
    notebook_id: int
    page_number: int
    page_id: Optional[int] = None  # DB ID of the page
    confidence: float = 1.0
    bounding_box: Optional[Dict] = None  # {x, y, width, height}
    existing_id: Optional[int] = None  # If this matches an existing todo
    date_extracted: Optional[str] = None
    completed: bool = False


class IntelligentTodoDeduplicator:
    """Handles intelligent deduplication of todos with OCR variations."""

    def __init__(
        self,
        similarity_threshold: float = 0.8,
        position_threshold: float = 50.0,
        confidence_improvement_threshold: float = 0.1,
    ):
        """
        Initialize the deduplicator.

        Args:
            similarity_threshold: Minimum similarity score (0-1) to consider todos as duplicates
            position_threshold: Maximum pixel distance to consider todos in same position
            confidence_improvement_threshold: Minimum confidence improvement to replace existing todo
        """
        self.similarity_threshold = similarity_threshold
        self.position_threshold = position_threshold
        self.confidence_improvement_threshold = confidence_improvement_threshold

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two todo texts using multiple methods.

        Returns a score from 0.0 (completely different) to 1.0 (identical).
        """
        if not text1 or not text2:
            return 0.0

        # Normalize texts for comparison
        norm1 = self._normalize_text(text1)
        norm2 = self._normalize_text(text2)

        if norm1 == norm2:
            return 1.0

        # Use SequenceMatcher for basic similarity
        basic_similarity = SequenceMatcher(None, norm1, norm2).ratio()

        # Boost score for common OCR substitution patterns
        ocr_adjusted_similarity = self._adjust_for_ocr_patterns(
            text1, text2, basic_similarity
        )

        # Consider word order and structure
        word_similarity = self._calculate_word_similarity(norm1, norm2)

        # Combined score with weighting
        final_score = (
            0.5 * ocr_adjusted_similarity + 0.3 * word_similarity + 0.2 * basic_similarity
        )

        return min(1.0, final_score)

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison by removing extra whitespace and standardizing case."""
        if not text:
            return ""

        # Remove extra whitespace and normalize case
        normalized = re.sub(r"\s+", " ", text.strip().lower())

        # Remove common OCR artifacts
        normalized = re.sub(r"[^\w\s:.-]", "", normalized)

        return normalized

    def _adjust_for_ocr_patterns(
        self, text1: str, text2: str, base_score: float
    ) -> float:
        """Adjust similarity score based on common OCR substitution patterns."""

        # Common OCR character substitutions
        ocr_substitutions = [
            ("l", "1", "I"),  # l, 1, I confusion
            ("O", "0", "Q"),  # O, 0, Q confusion
            ("rn", "m"),  # rn vs m
            ("cl", "d"),  # cl vs d
            ("nn", "n"),  # double n vs single n
            ("vv", "w"),  # vv vs w
        ]

        text1_lower = text1.lower()
        text2_lower = text2.lower()

        # Check if the difference can be explained by OCR substitutions
        for substitutions in ocr_substitutions:
            for i, sub1 in enumerate(substitutions):
                for sub2 in substitutions[i + 1 :]:
                    # Check both directions
                    if text1_lower.replace(sub1, sub2) == text2_lower:
                        return min(1.0, base_score + 0.2)  # Boost score
                    if text2_lower.replace(sub1, sub2) == text1_lower:
                        return min(1.0, base_score + 0.2)  # Boost score

        return base_score

    def _calculate_word_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity based on word overlap."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def calculate_position_distance(
        self, bbox1: Optional[Dict], bbox2: Optional[Dict]
    ) -> float:
        """Calculate distance between two bounding boxes."""
        if not bbox1 or not bbox2:
            return float("inf")

        # Calculate center points
        center1_x = bbox1.get("x", 0) + bbox1.get("width", 0) / 2
        center1_y = bbox1.get("y", 0) + bbox1.get("height", 0) / 2
        center2_x = bbox2.get("x", 0) + bbox2.get("width", 0) / 2
        center2_y = bbox2.get("y", 0) + bbox2.get("height", 0) / 2

        # Euclidean distance
        distance = ((center1_x - center2_x) ** 2 + (center1_y - center2_y) ** 2) ** 0.5
        return distance

    def find_similar_todos(
        self, new_todo: TodoCandidate, existing_todos: List[Dict]
    ) -> List[Tuple[Dict, float]]:
        """
        Find existing todos that are similar to a new candidate.

        Returns list of (existing_todo, similarity_score) tuples sorted by similarity.
        """
        similarities = []

        for existing in existing_todos:
            # Only compare todos from the same page
            if existing.get("page_number") != new_todo.page_number:
                continue

            # Calculate text similarity
            text_similarity = self.calculate_similarity(
                new_todo.text, existing.get("text", "")
            )

            if text_similarity < self.similarity_threshold:
                continue

            # Calculate position similarity if bounding boxes available
            position_bonus = 0.0
            if new_todo.bounding_box and existing.get("bounding_box"):
                try:
                    existing_bbox = existing.get("bounding_box")
                    if isinstance(existing_bbox, str):
                        import json

                        existing_bbox = json.loads(existing_bbox)

                    distance = self.calculate_position_distance(
                        new_todo.bounding_box, existing_bbox
                    )
                    if distance <= self.position_threshold:
                        position_bonus = 0.1  # Boost for same position
                except (ValueError, TypeError) as e:
                    logger.debug(f"Error parsing bounding box: {e}")

            final_similarity = min(1.0, text_similarity + position_bonus)
            similarities.append((existing, final_similarity))

        # Sort by similarity score (highest first)
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities

    def deduplicate_todos_for_page(
        self, new_todos: List[TodoCandidate], existing_todos: List[Dict]
    ) -> Tuple[List[TodoCandidate], List[int]]:
        """
        Match a page's newly extracted todos against its stored ones.

        Each stored todo is matched by at most one new todo (the first similar
        one), so two identical lines stay two todos.

        Returns:
            - Every new todo. One that matched a stored todo (the same todo,
              possibly with changed text) has ``existing_id`` set.
            - IDs of stored todos no new todo matched: they are no longer on
              the page.
        """
        final_todos = []
        matched_ids = set()

        for new_todo in new_todos:
            similar_todos = [
                (existing, score)
                for existing, score in self.find_similar_todos(new_todo, existing_todos)
                if existing.get("id") not in matched_ids
            ]

            if not similar_todos:
                # No similar todos found, add as new
                final_todos.append(new_todo)
                logger.debug(f"Adding new unique todo: {new_todo.text[:50]}...")
                continue

            # Find best match
            best_match, best_similarity = similar_todos[0]
            new_todo.existing_id = best_match.get("id")
            matched_ids.add(new_todo.existing_id)

            logger.debug(
                f"Matched todo (similarity: {best_similarity:.3f}): '{best_match.get('text', '')[:50]}...' -> '{new_todo.text[:50]}...'"
            )
            final_todos.append(new_todo)

        todos_to_delete = [
            existing["id"]
            for existing in existing_todos
            if existing.get("id") is not None and existing["id"] not in matched_ids
        ]
        return final_todos, todos_to_delete


def create_todo_candidate(
    text: str,
    notebook_id: int,
    page_number: int,
    page_id: Optional[int] = None,
    confidence: float = 1.0,
    bounding_box: Optional[Dict] = None,
    date_extracted: Optional[str] = None,
    completed: bool = False,
) -> TodoCandidate:
    """Helper function to create TodoCandidate from extraction results."""
    return TodoCandidate(
        text=text,
        notebook_id=notebook_id,
        page_number=page_number,
        page_id=page_id,
        confidence=confidence,
        bounding_box=bounding_box,
        date_extracted=date_extracted,
        completed=completed,
    )
