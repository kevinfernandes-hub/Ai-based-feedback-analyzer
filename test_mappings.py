#!/usr/bin/env python3
"""Test semantic MBA mapping logic for various question types."""

import sys
sys.path.insert(0, '/Users/kevinfernandes/Documents/ai feedback analyser/Ai-based-feedback-analyzer')

from app import (
    tokenize_text, score_outcomes, score_po_outcomes, 
    infer_question_theme, fallback_mappings_for_question
)

TEST_QUESTIONS = [
    ("How clearly were the concepts in SQL explained?", "SQL / Database"),
    ("How effectively did SQL improve your understanding of key topics?", "SQL / Database"),
    ("What tools and software were used in the lab?", "Lab / Tools"),
    ("How well did the team collaborate on the project?", "Teamwork / Project"),
    ("What is your assessment of ethical considerations in the case study?", "Ethics"),
    ("How would you design a solution to this problem?", "Design"),
    ("What evidence supports your analysis of this issue?", "Research / Analysis"),
    ("How would you communicate these results to stakeholders?", "Communication"),
]

def test_mappings():
    print("=" * 80)
    print("SEMANTIC NBA OUTCOME MAPPING TEST")
    print("=" * 80)
    
    for question_text, category in TEST_QUESTIONS:
        print(f"\n📌 Category: {category}")
        print(f"❓ Question: {question_text}")
        
        # Test each scoring function
        co_scores = score_outcomes(question_text, course_name="SQL")
        po_scores = score_po_outcomes(question_text)
        semantic = infer_question_theme(question_text)
        fallback = fallback_mappings_for_question(question_text, course_name="SQL")
        
        print(f"   CO outcomes: {co_scores[:4]}")
        print(f"   PO outcomes: {po_scores[:4]}")
        print(f"   Semantic theme: {semantic}")
        print(f"   Fallback mapping: {fallback[:5]}")
        
        # Show if results are diverse
        all_codes = set(fallback[:5])
        po_codes = [c for c in all_codes if c.startswith('PO')]
        co_codes = [c for c in all_codes if c.startswith('CO')]
        
        diversity = "✅ DIVERSE" if len(po_codes) > 1 or len(co_codes) > 1 else "⚠️  LIMITED"
        print(f"   Result: {diversity} - {', '.join(sorted(all_codes))}")

if __name__ == "__main__":
    test_mappings()
    print("\n" + "=" * 80)
    print("✅ Semantic mapping test complete!")
