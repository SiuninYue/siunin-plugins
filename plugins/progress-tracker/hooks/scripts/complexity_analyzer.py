#!/usr/bin/env python3
"""
Project complexity analysis with caching.

This module provides fast complexity assessment for features by caching
analysis results. This significantly improves performance for large projects
where complexity analysis might involve scanning many files.

Features:
- Complexity assessment based on multiple metrics
- Disk-based caching with TTL
- Cache invalidation on project changes
- JSON serialization for easy inspection
"""

import json
import hashlib
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional


class ComplexityAnalyzer:
    """
    Analyze feature complexity with intelligent caching.

    Complexity levels:
    - simple: Single file, clear requirements, <3 test steps
    - standard: Multiple files, 3-5 test steps, some design decisions
    - complex: >5 files, >5 test steps, significant architecture decisions

    Cache TTL is 1 hour by default.
    """

    # Cache expiration time
    CACHE_TTL = timedelta(hours=1)

    # Complexity thresholds
    SIMPLE_MAX_FILES = 1
    SIMPLE_MAX_STEPS = 3
    COMPLEX_MIN_FILES = 5
    COMPLEX_MIN_STEPS = 5

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the complexity analyzer.

        Args:
            cache_dir: Directory for cache storage. Defaults to .claude/.cache/
        """
        if cache_dir is None:
            # Default to .claude/.cache/ in current directory
            self.cache_dir = Path.cwd() / ".claude" / ".cache"
        else:
            self.cache_dir = Path(cache_dir)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "complexity_cache.json"

    def _get_cache_key(self, feature_description: str, test_steps: List[str]) -> str:
        """
        Generate a cache key from feature description and test steps.

        Args:
            feature_description: The feature description text
            test_steps: List of test step strings

        Returns:
            SHA256 hash of the combined content
        """
        content = f"{feature_description}|{'|'.join(test_steps)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _load_cache(self) -> Dict:
        """Load the cache from disk, returning empty dict if file doesn't exist."""
        if not self.cache_file.exists():
            return {}

        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)

            # Filter out expired entries
            now = datetime.now()
            valid_cache = {}

            for key, entry in cache.items():
                try:
                    cached_time = datetime.fromisoformat(entry.get('timestamp', ''))
                    age = now - cached_time

                    if age < self.CACHE_TTL:
                        valid_cache[key] = entry
                except (ValueError, KeyError):
                    # Skip invalid entries
                    continue

            return valid_cache

        except (json.JSONDecodeError, IOError):
            return {}

    def _save_cache(self, cache: Dict) -> None:
        """Save the cache to disk."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
        except IOError:
            # Fail silently - caching is optional
            pass

    def _calculate_metrics(self, feature_description: str, test_steps: List[str]) -> Dict:
        """
        Calculate complexity metrics from feature description and test steps.

        Args:
            feature_description: The feature description text
            test_steps: List of test step strings

        Returns:
            Dictionary of complexity metrics
        """
        # Analyze description
        desc_lower = feature_description.lower()
        desc_words = feature_description.split()

        # Complexity indicators in description
        design_keywords = [
            'architecture', 'design', 'pattern', 'refactor',
            'optimize', 'integration', 'migration', 'implement'
        ]
        complex_keywords = [
            'system', 'multiple', 'distributed', 'async',
            'concurrent', 'scalable', 'performance', 'security'
        ]

        design_score = sum(1 for kw in design_keywords if kw in desc_lower)
        complex_score = sum(1 for kw in complex_keywords if kw in desc_lower)

        # Analyze test steps
        num_steps = len(test_steps)
        avg_step_length = sum(len(step.split()) for step in test_steps) / max(num_steps, 1)

        # Count technical terms in test steps
        technical_terms = 0
        for step in test_steps:
            step_lower = step.lower()
            technical_terms += sum(1 for term in ['api', 'database', 'sql', 'http', 'json', 'auth']
                                   if term in step_lower)

        # Estimate file changes from description
        file_indicators = [
            ('file', 1), ('class', 1), ('function', 1), ('method', 1),
            ('module', 1), ('package', 1), ('component', 1), ('service', 1),
            ('model', 1), ('view', 1), ('controller', 1), ('route', 1),
            ('test', 1), ('spec', 1), ('migration', 2), ('schema', 2)
        ]

        estimated_files = 1  # Base: at least one file
        for indicator, count in file_indicators:
            estimated_files += desc_lower.count(indicator) * count

        # Cap reasonable maximum
        estimated_files = min(estimated_files, 20)

        return {
            'description_length': len(feature_description),
            'description_word_count': len(desc_words),
            'design_score': design_score,
            'complex_score': complex_score,
            'num_steps': num_steps,
            'avg_step_length': avg_step_length,
            'technical_terms': technical_terms,
            'estimated_files': estimated_files,
            'has_api': 'api' in desc_lower,
            'has_database': 'database' in desc_lower or 'sql' in desc_lower,
            'has_auth': 'auth' in desc_lower or 'login' in desc_lower or 'security' in desc_lower,
        }

    def _determine_complexity(self, metrics: Dict) -> Tuple[str, str]:
        """
        Determine complexity level and reason from metrics.

        Args:
            metrics: Dictionary of complexity metrics

        Returns:
            Tuple of (complexity_level, reason)
        """
        # Calculate a weighted score
        score = (
            metrics['estimated_files'] * 2 +
            metrics['num_steps'] * 1.5 +
            metrics['design_score'] * 3 +
            metrics['complex_score'] * 2 +
            metrics['technical_terms'] * 0.5
        )

        # Decision boundaries
        if score <= 8:
            return 'simple', self._simple_reason(metrics)
        elif score <= 18:
            return 'standard', self._standard_reason(metrics)
        else:
            return 'complex', self._complex_reason(metrics)

    def _simple_reason(self, metrics: Dict) -> str:
        """Generate explanation for simple complexity."""
        reasons = []

        if metrics['estimated_files'] <= self.SIMPLE_MAX_FILES:
            reasons.append(f"single file change (~{metrics['estimated_files']} file)")
        if metrics['num_steps'] <= self.SIMPLE_MAX_STEPS:
            reasons.append(f"few test steps ({metrics['num_steps']})")
        if metrics['design_score'] == 0:
            reasons.append("no design decisions needed")

        if not reasons:
            reasons.append("straightforward implementation")

        return ", ".join(reasons)

    def _standard_reason(self, metrics: Dict) -> str:
        """Generate explanation for standard complexity."""
        reasons = []

        if self.SIMPLE_MAX_FILES < metrics['estimated_files'] < self.COMPLEX_MIN_FILES:
            reasons.append(f"multiple files (~{metrics['estimated_files']} files)")
        if self.SIMPLE_MAX_STEPS < metrics['num_steps'] < self.COMPLEX_MIN_STEPS:
            reasons.append(f"moderate test coverage ({metrics['num_steps']} steps)")
        if metrics['design_score'] > 0:
            reasons.append("some design considerations")

        if not reasons:
            reasons.append("standard implementation effort")

        return ", ".join(reasons)

    def _complex_reason(self, metrics: Dict) -> str:
        """Generate explanation for complex complexity."""
        reasons = []

        if metrics['estimated_files'] >= self.COMPLEX_MIN_FILES:
            reasons.append(f"many files involved (~{metrics['estimated_files']} files)")
        if metrics['num_steps'] >= self.COMPLEX_MIN_STEPS:
            reasons.append(f"extensive testing ({metrics['num_steps']} steps)")
        if metrics['design_score'] >= 2:
            reasons.append("significant architecture decisions")
        if metrics['complex_score'] >= 2:
            reasons.append("complex technical requirements")
        if metrics['has_api']:
            reasons.append("API integration")
        if metrics['has_database']:
            reasons.append("database changes")
        if metrics['has_auth']:
            reasons.append("authentication/security")

        if not reasons:
            reasons.append("complex implementation")

        return ", ".join(reasons)

    def analyze_complexity(
        self,
        feature_description: str,
        test_steps: List[str],
        use_cache: bool = True
    ) -> Tuple[str, str, Dict]:
        """
        Analyze feature complexity with caching.

        Args:
            feature_description: Description of the feature to analyze
            test_steps: List of test steps for the feature
            use_cache: Whether to use cached results (default: True)

        Returns:
            Tuple of (complexity_level, reason, metrics)
            - complexity_level: 'simple', 'standard', or 'complex'
            - reason: Human-readable explanation
            - metrics: Full metrics dictionary
        """
        cache_key = self._get_cache_key(feature_description, test_steps)

        # Check cache if enabled
        if use_cache:
            cache = self._load_cache()

            if cache_key in cache:
                entry = cache[cache_key]
                return (
                    entry['complexity'],
                    entry['reason'],
                    entry.get('metrics', {})
                )

        # Calculate metrics
        metrics = self._calculate_metrics(feature_description, test_steps)

        # Determine complexity
        complexity, reason = self._determine_complexity(metrics)

        # Cache the result
        if use_cache:
            cache = self._load_cache()
            cache[cache_key] = {
                'complexity': complexity,
                'reason': reason,
                'metrics': metrics,
                'timestamp': datetime.now().isoformat()
            }
            self._save_cache(cache)

        return complexity, reason, metrics

    def clear_cache(self) -> None:
        """Clear the complexity cache."""
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
            except IOError:
                pass

    def get_cache_stats(self) -> Dict:
        """Get statistics about the cache."""
        cache = self._load_cache()

        if not cache:
            return {
                'entries': 0,
                'size_bytes': 0,
                'oldest_entry': None,
                'newest_entry': None
            }

        timestamps = []
        for entry in cache.values():
            try:
                timestamps.append(datetime.fromisoformat(entry['timestamp']))
            except (ValueError, KeyError):
                continue

        file_size = self.cache_file.stat().st_size if self.cache_file.exists() else 0

        return {
            'entries': len(cache),
            'size_bytes': file_size,
            'oldest_entry': min(timestamps).isoformat() if timestamps else None,
            'newest_entry': max(timestamps).isoformat() if timestamps else None
        }


# Convenience function for quick complexity checks
def quick_complexity_check(feature_description: str, test_steps: List[str]) -> str:
    """
    Quick complexity check without caching concerns.

    Args:
        feature_description: Feature description
        test_steps: List of test steps

    Returns:
        Complexity level: 'simple', 'standard', or 'complex'
    """
    analyzer = ComplexityAnalyzer()
    complexity, _, _ = analyzer.analyze_complexity(feature_description, test_steps)
    return complexity


if __name__ == "__main__":
    # Simple CLI for testing
    import sys

    if len(sys.argv) < 3:
        print("Usage: python complexity_analyzer.py '<description>' '<step1>' '<step2>' ...")
        sys.exit(1)

    description = sys.argv[1]
    steps = sys.argv[2:] if len(sys.argv) > 2 else []

    analyzer = ComplexityAnalyzer()
    complexity, reason, metrics = analyzer.analyze_complexity(description, steps)

    print(f"Complexity: {complexity}")
    print(f"Reason: {reason}")
    print(f"\nMetrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
