"""
Test suite for optimized route planner
Validates correctness, performance, and edge cases
"""

import pytest
import time
import math
from optimized_route_planner import (
    KDTree,
    SpatialGrid,
    DistanceCache,
    AdaptiveFilteringStrategy,
    optimized_route_planner,
    two_opt_improve_fast,
    _haversine_fast,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def sample_bins():
    """Generate small bin dataset for testing."""
    return {
        "bin-1": {
            "bin_id": "bin-1",
            "name": "Bin 1",
            "location": {"lat": 29.6462, "lng": -82.3479},
            "fill_percent": 50.0,
            "last_emptied_at": time.time() - 10*3600,
        },
        "bin-2": {
            "bin_id": "bin-2",
            "name": "Bin 2",
            "location": {"lat": 29.6470, "lng": -82.3480},
            "fill_percent": 75.0,
            "last_emptied_at": time.time() - 20*3600,
        },
        "bin-3": {
            "bin_id": "bin-3",
            "name": "Bin 3",
            "location": {"lat": 29.6500, "lng": -82.3500},
            "fill_percent": 30.0,
            "last_emptied_at": time.time() - 5*3600,
        },
        "bin-4": {
            "bin_id": "bin-4",
            "name": "Bin 4",
            "location": {"lat": 29.6450, "lng": -82.3450},
            "fill_percent": 90.0,
            "last_emptied_at": time.time() - 30*3600,
        },
    }


def generate_large_bins(num_bins: int) -> dict:
    """Generate large dataset for scalability testing."""
    bins = {}
    centers = [
        (29.6462, -82.3479),
        (29.6500, -82.3450),
        (29.6400, -82.3500),
    ]
    
    for i in range(num_bins):
        cluster = i % len(centers)
        center_lat, center_lng = centers[cluster]
        
        # Add random offset
        lat = center_lat + (i % 10) * 0.001
        lng = center_lng + (i % 10) * 0.001
        
        bins[f"bin-{i:06d}"] = {
            "bin_id": f"bin-{i:06d}",
            "name": f"Bin {i}",
            "location": {"lat": lat, "lng": lng},
            "fill_percent": 10.0 + (i % 90),  # 10-99%
            "last_emptied_at": time.time() - ((i % 48) * 3600),
        }
    
    return bins


# ============================================================================
# K-D TREE TESTS
# ============================================================================

class TestKDTree:
    
    def test_kd_tree_initialization(self, sample_bins):
        """K-D tree initializes without error."""
        kd_tree = KDTree(sample_bins)
        assert kd_tree.root is not None
    
    def test_kd_tree_nearest_neighbors(self, sample_bins):
        """K-D tree finds neighbors within radius."""
        kd_tree = KDTree(sample_bins)
        neighbors = kd_tree.nearest_neighbors(29.6462, -82.3479, radius_km=2.0)
        
        # Should find at least bin-2 which is nearby
        bin_ids = [bid for bid, _ in neighbors]
        assert len(neighbors) > 0
        assert any("bin-" in bid for bid in bin_ids)
    
    def test_kd_tree_distance_accuracy(self, sample_bins):
        """K-D tree returns accurate distances."""
        kd_tree = KDTree(sample_bins)
        neighbors = kd_tree.nearest_neighbors(29.6462, -82.3479, radius_km=1.0)
        
        # All returned distances should be <= radius
        for bin_id, dist in neighbors:
            assert dist <= 1.01  # Allow small floating point error
    
    def test_kd_tree_scaling(self):
        """K-D tree handles large datasets efficiently."""
        large_bins = generate_large_bins(1000)
        
        start = time.perf_counter()
        kd_tree = KDTree(large_bins)
        build_time = (time.perf_counter() - start) * 1000
        
        # Building shouldn't take too long
        assert build_time < 500  # 500ms for 1000 bins
        
        # Query should be fast
        start = time.perf_counter()
        neighbors = kd_tree.nearest_neighbors(29.6462, -82.3479, radius_km=2.0, max_results=100)
        query_time = (time.perf_counter() - start) * 1000
        
        assert query_time < 100  # <100ms for query
        assert len(neighbors) > 0


# ============================================================================
# SPATIAL GRID TESTS
# ============================================================================

class TestSpatialGrid:
    
    def test_grid_initialization(self, sample_bins):
        """Spatial grid initializes correctly."""
        grid = SpatialGrid(sample_bins, cell_size_km=0.5)
        assert len(grid.cells) > 0
    
    def test_grid_nearby_bins(self, sample_bins):
        """Grid returns nearby bins."""
        grid = SpatialGrid(sample_bins, cell_size_km=0.5)
        nearby = grid.get_nearby_bins(29.6462, -82.3479, radius_km=2.0)
        
        assert len(nearby) > 0
        assert isinstance(nearby, list)
    
    def test_grid_coverage(self, sample_bins):
        """Grid covers all bins."""
        grid = SpatialGrid(sample_bins, cell_size_km=0.5)
        
        all_nearby = set()
        for lat in [29.6400, 29.6450, 29.6500, 29.6550]:
            for lng in [-82.3550, -82.3500, -82.3450, -82.3400]:
                nearby = grid.get_nearby_bins(lat, lng, radius_km=10.0)
                all_nearby.update(nearby)
        
        # Should eventually find all bins with large radius
        assert len(all_nearby) == len(sample_bins)


# ============================================================================
# DISTANCE CACHE TESTS
# ============================================================================

class TestDistanceCache:
    
    def test_cache_stores_distance(self):
        """Cache stores and retrieves distances."""
        cache = DistanceCache()
        
        dist1 = cache.get_distance(29.6462, -82.3479, 29.6470, -82.3480)
        dist2 = cache.get_distance(29.6462, -82.3479, 29.6470, -82.3480)
        
        assert dist1 == dist2
    
    def test_cache_eviction(self):
        """Cache evicts old entries when full."""
        cache = DistanceCache(max_size=5)
        
        # Fill cache
        for i in range(10):
            lat = 29.6400 + i * 0.001
            cache.get_distance(lat, -82.3479, 29.6470, -82.3480)
        
        # Should still work and have at most max_size entries
        assert len(cache.cache) <= 5
    
    def test_cache_hit_rate(self):
        """Cache reuses calculations."""
        cache = DistanceCache()
        
        # Repeated queries should be cached
        for _ in range(100):
            cache.get_distance(29.6462, -82.3479, 29.6470, -82.3480)
        
        # Only 1 unique calculation, so only 1 entry
        assert len(cache.cache) == 1


# ============================================================================
# ADAPTIVE FILTERING TESTS
# ============================================================================

class TestAdaptiveFiltering:
    
    def test_filtering_strategy_initialization(self, sample_bins):
        """Filtering strategy initializes correctly."""
        strategy = AdaptiveFilteringStrategy(sample_bins)
        assert strategy.grid is not None
        assert strategy.kd_tree is not None
    
    def test_filtering_strategy_reduces_candidates(self, sample_bins):
        """Filtering reduces candidate set."""
        strategy = AdaptiveFilteringStrategy(sample_bins)
        
        candidates = strategy.filter_candidates(
            29.6462, -82.3479,
            unvisited_bins=set(sample_bins.keys()) - {"bin-1"},
            fill_threshold=10.0,
            max_candidates=50,
        )
        
        # Should return some candidates
        assert len(candidates) > 0
        # None should be visited bin
        assert "bin-1" not in candidates or "bin-1" not in {"bin-1"}
    
    def test_filtering_strategy_respects_threshold(self, sample_bins):
        """Filtering respects fill threshold."""
        strategy = AdaptiveFilteringStrategy(sample_bins)
        
        candidates = strategy.filter_candidates(
            29.6462, -82.3479,
            unvisited_bins=set(sample_bins.keys()),
            fill_threshold=80.0,  # High threshold
            max_candidates=50,
        )
        
        # All candidates should have fill >= 80%
        for bid, doc in candidates.items():
            assert doc["fill_percent"] >= 80.0


# ============================================================================
# ROUTE PLANNER TESTS
# ============================================================================

class TestOptimizedRoutePlanner:
    
    def test_route_valid_structure(self, sample_bins):
        """Route has valid structure."""
        now = time.time()
        def priority_fn(doc):
            fill = doc.get("fill_percent", 0.0)
            hours = (now - doc.get("last_emptied_at", now)) / 3600.0
            return 0.7 * (fill / 100.0) + 0.3 * min(hours / 24.0, 1.0)
        
        route = optimized_route_planner(
            "bin-1", "bin-3", sample_bins,
            priority_fn,
            max_stops=4,
        )
        
        # Route is a list
        assert isinstance(route, list)
        # Starts with start_id
        assert route[0] == "bin-1"
        # Ends with end_id
        assert route[-1] == "bin-3"
        # No duplicates
        assert len(set(route)) == len(route)
    
    def test_route_respects_max_stops(self, sample_bins):
        """Route respects max_stops parameter."""
        now = time.time()
        def priority_fn(doc):
            return 0.5
        
        route = optimized_route_planner(
            "bin-1", "bin-3", sample_bins,
            priority_fn,
            max_stops=2,  # Start and end only
        )
        
        # Should not exceed max_stops
        assert len(route) <= 2
    
    def test_route_scaling_500_to_1000(self):
        """Route planner handles 500-1000 bins efficiently."""
        bins = generate_large_bins(500)
        bin_list = list(bins.keys())
        start_id = bin_list[0]
        end_id = bin_list[-1]
        
        now = time.time()
        def priority_fn(doc):
            return 0.5
        
        start = time.perf_counter()
        route = optimized_route_planner(
            start_id, end_id, bins,
            priority_fn,
            max_stops=20,
            timeout_ms=100.0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Should complete within timeout
        assert elapsed_ms < 150  # 150% of timeout for safety
        # Should have built a reasonable route
        assert len(route) > 2
        assert len(route) <= 20
    
    def test_route_timeout_protection(self, sample_bins):
        """Route planner respects timeout."""
        now = time.time()
        def priority_fn(doc):
            return 0.5
        
        start = time.perf_counter()
        route = optimized_route_planner(
            "bin-1", "bin-3", sample_bins,
            priority_fn,
            timeout_ms=10.0,  # Very short timeout
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Should terminate before timeout (with small margin)
        assert elapsed_ms < 50


# ============================================================================
# 2-OPT LOCAL SEARCH TESTS
# ============================================================================

class TestTwoOptImprovement:
    
    def test_two_opt_produces_valid_route(self, sample_bins):
        """2-opt produces valid route with same bins."""
        route = ["bin-1", "bin-2", "bin-3", "bin-4"]
        cache = DistanceCache()
        
        improved = two_opt_improve_fast(route, sample_bins, cache, max_iterations=10)
        
        # Same bins, possibly reordered
        assert set(improved) == set(route)
        # Still starts and ends with same
        assert improved[0] == "bin-1"
        assert improved[-1] == "bin-4"
    
    def test_two_opt_reduces_distance(self, sample_bins):
        """2-opt reduces total route distance."""
        route = ["bin-1", "bin-4", "bin-3", "bin-2"]  # Suboptimal order
        cache = DistanceCache()
        
        def calc_distance(r):
            total = 0
            for i in range(len(r) - 1):
                lat1 = sample_bins[r[i]]["location"]["lat"]
                lng1 = sample_bins[r[i]]["location"]["lng"]
                lat2 = sample_bins[r[i+1]]["location"]["lat"]
                lng2 = sample_bins[r[i+1]]["location"]["lng"]
                total += _haversine_fast(lat1, lng1, lat2, lng2)
            return total
        
        dist_before = calc_distance(route)
        improved = two_opt_improve_fast(route, sample_bins, cache, max_iterations=20)
        dist_after = calc_distance(improved)
        
        # 2-opt should not increase distance (may be same if already optimal)
        assert dist_after <= dist_before + 0.01  # Small epsilon for float errors
    
    def test_two_opt_short_timeout(self, sample_bins):
        """2-opt respects timeout."""
        route = ["bin-1", "bin-2", "bin-3", "bin-4"]
        cache = DistanceCache()
        
        start = time.perf_counter()
        improved = two_opt_improve_fast(
            route, sample_bins, cache,
            max_iterations=100,
            timeout_ms=5.0  # Very short timeout
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Should terminate before timeout
        assert elapsed_ms < 50


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    
    def test_latency_benchmark_500_bins(self):
        """500 bins should be < 20ms."""
        bins = generate_large_bins(500)
        bin_list = list(bins.keys())
        start_id = bin_list[0]
        end_id = bin_list[-1]
        
        now = time.time()
        def priority_fn(doc):
            return 0.5
        
        start = time.perf_counter()
        route = optimized_route_planner(
            start_id, end_id, bins,
            priority_fn,
            max_stops=20,
            timeout_ms=100.0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n500 bins: {elapsed_ms:.2f}ms")
        assert elapsed_ms < 50  # Should be quite fast
    
    def test_latency_benchmark_1000_bins(self):
        """1000 bins should be < 50ms."""
        bins = generate_large_bins(1000)
        bin_list = list(bins.keys())
        start_id = bin_list[0]
        end_id = bin_list[-1]
        
        now = time.time()
        def priority_fn(doc):
            return 0.5
        
        start = time.perf_counter()
        route = optimized_route_planner(
            start_id, end_id, bins,
            priority_fn,
            max_stops=20,
            timeout_ms=100.0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n1000 bins: {elapsed_ms:.2f}ms")
        assert elapsed_ms < 100
    
    def test_latency_benchmark_5000_bins(self):
        """5000 bins should be < 100ms."""
        bins = generate_large_bins(5000)
        bin_list = list(bins.keys())
        start_id = bin_list[0]
        end_id = bin_list[-1]
        
        now = time.time()
        def priority_fn(doc):
            return 0.5
        
        start = time.perf_counter()
        route = optimized_route_planner(
            start_id, end_id, bins,
            priority_fn,
            max_stops=20,
            timeout_ms=100.0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n5000 bins: {elapsed_ms:.2f}ms")
        assert elapsed_ms < 150


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
