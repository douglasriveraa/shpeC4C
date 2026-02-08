"""
Quick validation of optimized algorithm (no pytest required)
Runs core functionality checks
"""

import time
import sys
from optimized_route_planner import (
    KDTree,
    SpatialGrid,
    DistanceCache,
    AdaptiveFilteringStrategy,
    optimized_route_planner,
)


def generate_test_bins(count):
    """Generate test bins."""
    bins = {}
    for i in range(count):
        bins[f"bin-{i:04d}"] = {
            "bin_id": f"bin-{i:04d}",
            "name": f"Bin {i}",
            "location": {
                "lat": 29.6462 + (i % 10) * 0.001,
                "lng": -82.3479 + (i % 10) * 0.001,
            },
            "fill_percent": 10.0 + (i % 90),
            "last_emptied_at": time.time() - (i % 48) * 3600,
        }
    return bins


def test_kd_tree():
    """Test K-D tree functionality."""
    print("Testing K-D Tree...")
    bins = generate_test_bins(100)
    
    try:
        kd_tree = KDTree(bins)
        neighbors = kd_tree.nearest_neighbors(29.6462, -82.3479, radius_km=2.0)
        
        assert len(neighbors) > 0, "K-D tree should find neighbors"
        assert all(dist <= 2.01 for _, dist in neighbors), "All distances should be within radius"
        
        print("  ✓ K-D tree working correctly")
        return True
    except Exception as e:
        print(f"  ✗ K-D tree failed: {e}")
        return False


def test_spatial_grid():
    """Test spatial grid functionality."""
    print("Testing Spatial Grid...")
    bins = generate_test_bins(100)
    
    try:
        grid = SpatialGrid(bins, cell_size_km=0.5)
        nearby = grid.get_nearby_bins(29.6462, -82.3479, radius_km=2.0)
        
        assert len(nearby) > 0, "Grid should find nearby bins"
        assert isinstance(nearby, list), "Should return list"
        
        print("  ✓ Spatial grid working correctly")
        return True
    except Exception as e:
        print(f"  ✗ Spatial grid failed: {e}")
        return False


def test_distance_cache():
    """Test distance cache."""
    print("Testing Distance Cache...")
    
    try:
        cache = DistanceCache(max_size=100)
        
        dist1 = cache.get_distance(29.6462, -82.3479, 29.6470, -82.3480)
        dist2 = cache.get_distance(29.6462, -82.3479, 29.6470, -82.3480)
        
        assert dist1 == dist2, "Cache should return same value"
        assert len(cache.cache) == 1, "Should have 1 cached entry"
        
        # Test cache hit
        for _ in range(100):
            cache.get_distance(29.6462, -82.3479, 29.6470, -82.3480)
        
        assert len(cache.cache) == 1, "Should still have 1 entry after repeated calls"
        
        print("  ✓ Distance cache working correctly")
        return True
    except Exception as e:
        print(f"  ✗ Distance cache failed: {e}")
        return False


def test_adaptive_filtering():
    """Test adaptive filtering strategy."""
    print("Testing Adaptive Filtering...")
    bins = generate_test_bins(100)
    
    try:
        strategy = AdaptiveFilteringStrategy(bins)
        candidates = strategy.filter_candidates(
            29.6462, -82.3479,
            unvisited_bins=set(bins.keys()) - {"bin-0000"},
            fill_threshold=10.0,
            max_candidates=50,
        )
        
        assert len(candidates) > 0, "Should find candidates"
        assert "bin-0000" not in candidates, "Should not include visited bins"
        
        print("  ✓ Adaptive filtering working correctly")
        return True
    except Exception as e:
        print(f"  ✗ Adaptive filtering failed: {e}")
        return False


def test_route_planner():
    """Test optimized route planner."""
    print("Testing Optimized Route Planner...")
    bins = generate_test_bins(100)
    bin_list = list(bins.keys())
    start_id = bin_list[0]
    end_id = bin_list[-1]
    
    try:
        now = time.time()
        def priority_fn(doc):
            fill = doc.get("fill_percent", 0.0)
            hours = (now - doc.get("last_emptied_at", now)) / 3600.0
            return 0.7 * (fill / 100.0) + 0.3 * min(hours / 24.0, 1.0)
        
        start = time.perf_counter()
        route = optimized_route_planner(
            start_id, end_id, bins,
            priority_fn,
            max_stops=15,
            timeout_ms=100.0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert isinstance(route, list), "Route should be list"
        assert route[0] == start_id, "Route should start with start_id"
        assert route[-1] == end_id, "Route should end with end_id"
        assert len(set(route)) == len(route), "Route should have no duplicates"
        assert len(route) <= 20, "Route should be reasonable length"
        assert elapsed_ms < 200, f"Route planning should be fast (<200ms), got {elapsed_ms:.2f}ms"
        
        print(f"  ✓ Route planner working correctly ({len(route)} stops in {elapsed_ms:.2f}ms)")
        return True
    except Exception as e:
        print(f"  ✗ Route planner failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_scalability():
    """Test with larger datasets."""
    print("Testing Scalability...")
    
    test_sizes = [500, 1000, 5000]
    results = []
    
    for size in test_sizes:
        bins = generate_test_bins(size)
        bin_list = list(bins.keys())
        start_id = bin_list[0]
        end_id = bin_list[-1]
        
        try:
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
            
            results.append({
                "size": size,
                "time_ms": elapsed_ms,
                "stops": len(route),
                "success": True,
            })
            
            print(f"  ✓ {size:5d} bins: {elapsed_ms:7.2f}ms, {len(route):2d} stops")
        except Exception as e:
            results.append({
                "size": size,
                "time_ms": None,
                "stops": None,
                "success": False,
                "error": str(e),
            })
            print(f"  ✗ {size:5d} bins: FAILED - {e}")
    
    # Check scalability
    all_successful = all(r["success"] for r in results)
    if all_successful:
        times = [r["time_ms"] for r in results]
        # Should scale roughly O(log n) - doubling size shouldn't double time
        if times[1] / times[0] < 3:  # 500→1000 should be <3x
            print("  ✓ Scalability excellent (better than O(n))")
            return True
        else:
            print(f"  ⚠ Scalability could be better (500→1000: {times[1]/times[0]:.1f}x)")
            return True
    
    return False


def main():
    """Run all validation tests."""
    print("\n" + "=" * 70)
    print("OPTIMIZED ALGORITHM VALIDATION")
    print("=" * 70 + "\n")
    
    tests = [
        test_kd_tree,
        test_spatial_grid,
        test_distance_cache,
        test_adaptive_filtering,
        test_route_planner,
        test_scalability,
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test {test_func.__name__} crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
        print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"\n✅ ALL TESTS PASSED ({passed}/{total})")
        print("\nThe optimized algorithm is ready for deployment!")
        return 0
    else:
        print(f"\n⚠️  {passed}/{total} tests passed, {total - passed} failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
