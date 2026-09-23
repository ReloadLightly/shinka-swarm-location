"""Reviewed fixed controls, not evolved programs or recovered chapter code.

No file/network/optimum access. All methods accept the same prepared DAG problem.
Method-specific compilation, warm starts, proof serialization and search are timed.
"""
from fractions import Fraction
import heapq
from math import isfinite
import random
from time import perf_counter

from .route_search import RouteSearch, RouteLimit, SearchDeadline, check_time

METHODS=('route_greedy','celf','route_swap','early_celf_swap','iterated','dfbnb','potential')
BOUND_METHODS=('dfbnb','potential')


def greedy(p,k,deadline,report,*,lazy=False):
    selected=[]; covered=0; counters={'gain_evaluations':0}
    if lazy:
        heap=[(-p.weight(bits),i,0) for i,bits in enumerate(p.covers)]
        heapq.heapify(heap); counters['gain_evaluations']+=len(heap)
        while heap and len(selected)<k:
            check_time(deadline)
            negative,i,stamp=heapq.heappop(heap)
            if stamp==len(selected):
                selected.append(i);covered |= p.covers[i];report(selected)
            else:
                gain=p.weight(p.covers[i] & ~covered);counters['gain_evaluations']+=1
                heapq.heappush(heap,(-gain,i,len(selected)))
    else:
        for _ in range(k):
            check_time(deadline)
            remaining=[i for i in range(len(p.nodes)) if i not in selected]
            gains=p.gains(covered,remaining);counters['gain_evaluations']+=len(gains)
            _,i=min(gains,key=lambda x:(-x[0],x[1]))
            selected.append(i);covered |= p.covers[i];report(selected)
    return tuple(selected),counters


def descent(p,selected,deadline,report):
    """Best strict 1-swap. Neutral/worse working moves belong only to iterated."""
    selected=tuple(sorted(selected));value=p.score(selected);swaps=0
    while selected:
        check_time(deadline)
        best_group,best=selected,value
        for removed in selected:
            check_time(deadline)
            rest=tuple(i for i in selected if i!=removed)
            covered=p.covered(rest);base=p.weight(covered)
            for added in range(len(p.nodes)):
                if added in selected:continue
                trial=base+p.weight(p.covers[added] & ~covered)
                if trial>best:
                    best_group,best=tuple(sorted((*rest,added))),trial
        if best<=value:return selected,swaps
        selected,value=best_group,best;swaps+=1;report(selected)
    return selected,swaps


def solve(problem,k,random_seed,report,time_budget,method,*,route_limit=20_000,max_cycles=None):
    if method not in METHODS:raise ValueError('unknown strong baseline')
    problem.instance.validate_budget(k)
    if type(random_seed) is not int:raise ValueError('integer seed required')
    if isinstance(time_budget,bool) or not isfinite(time_budget) or time_budget<0:
        raise ValueError('finite nonnegative time budget required')
    if max_cycles is not None and (type(max_cycles) is not int or max_cycles<0):
        raise ValueError('invalid cycle limit')
    started=perf_counter();deadline=started+time_budget
    best_ids=[];best_mass=-1
    bound_report=getattr(report,'bound',lambda _:None)
    diagnostic=getattr(report,'diagnostic',lambda _:None)
    stats={'method':method,'fallback':False,'route_limit':route_limit,'cycles':0,'accepted_worse_working_states':0}
    report([])
    if method in BOUND_METHODS:
        bound_report({'kind':'universal_v1','selected':[],'upper':'1' if k else '0'})
    if k==0:return []
    try:
        if method=='early_celf_swap':
            check_time(deadline)
            gains=problem.marginal_gains([])
            best_ids=sorted(gains,key=lambda v:(-gains[v],v))[:k]
            report(best_ids)
        prep=perf_counter()
        p=RouteSearch(problem,deadline=deadline,max_routes=route_limit)
        best_mass=p.score(p.indices(best_ids))
        stats.update(route_preparation_seconds=perf_counter()-prep,
            raw_shortest_routes=p.raw_routes,unique_route_masks=len(p.routes),route_visits=p.visits)
        diagnostic(dict(stats))
        def offer(group):
            nonlocal best_ids,best_mass
            value=p.score(group)
            if value>best_mass:
                best_ids=p.ids(group);best_mass=value;report(best_ids)
        selected,counts=greedy(p,k,deadline,offer,lazy=method!='route_greedy')
        stats.update(counts)
        if method in ('route_greedy','celf'):return best_ids
        selected,swaps=descent(p,selected,deadline,offer);stats['descent_swaps']=swaps
        if method in ('route_swap','early_celf_swap'):return best_ids
        if method in BOUND_METHODS:
            from .bounded_search import PartitionSearch
            tree=PartitionSearch(p,k,p.indices(best_ids),method)
            tree.run(report,bound_report,deadline)
            best_ids=p.ids(tree.best_group)
            stats.update(splits=tree.splits,expanded=tree.expanded,peak_open=tree.peak_open,
                         rekeys=tree.rekeys,search_termination=tree.termination)
            return best_ids
        rng=random.Random(random_seed);radius=1;working=selected
        while max_cycles is None or stats['cycles']<max_cycles:
            check_time(deadline)
            old_best=best_mass
            r=min(radius,k,len(p.nodes)-k)
            if r==0:break
            if radius>k:
                trial=tuple(sorted(rng.sample(range(len(p.nodes)),k)))
                radius=1
            else:
                removed=set(rng.sample(list(working),r))
                available=[i for i in range(len(p.nodes)) if i not in working]
                trial=tuple(sorted((set(working)-removed)|set(rng.sample(available,r))))
            if p.score(trial)<p.score(working):stats['accepted_worse_working_states']+=1
            offer(trial)
            working,swaps=descent(p,trial,deadline,offer)
            stats['descent_swaps']+=swaps;stats['cycles']+=1
            radius=1 if best_mass>old_best else radius+1
    except RouteLimit as exc:
        stats.update(fallback=True,fallback_reason=str(exc))
        diagnostic(dict(stats))
        from .anytime_baselines import solve as fixed
        remaining=max(0.,deadline-perf_counter())
        if remaining:
            # Keep the existing best through the independently scored report trace.
            result=fixed(problem,k,random_seed,report,remaining,'greedy_swap')
            if problem.score(result)>problem.score(best_ids):best_ids=list(result)
        return best_ids
    except SearchDeadline:
        stats['search_termination']='advisory_deadline'
    finally:
        stats['solver_wall_seconds']=perf_counter()-started
        if 'p' in locals():stats['uncached_weight_evaluations']=p.weight_calls
        diagnostic(stats)
    return best_ids
