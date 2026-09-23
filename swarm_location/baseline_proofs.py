"""Post-capture independent verification of bounds actually emitted during search.

Uses the pre-existing certificate representation, not the new solver's bound,
priority, frontier implementation, or stopping status. Exact arithmetic only.
Snapshots are stamped by the parent; verification time is not solver time.
"""
from fractions import Fraction
import heapq
from math import isfinite

from .certificates import ExactCoverage, rational
from .certificate_references import _IntegerRoutes


def verify_online_bounds(instance,k,events):
    instance.validate_budget(k)
    p=None; leaves={}; heap=[]; next_id=1; count=0; prior=-1; previous=Fraction(1)
    certified=[]

    def leaf(group,remaining,uncovered,value,inherited):
        slots=k-len(group)
        if slots<0:raise ValueError('partition cardinality exceeded')
        if slots==0 or not remaining:return (group,remaining,uncovered,value,value)
        union=0
        for v in remaining:union |= p.covers[v]
        possible=p.weight(union & uncovered)
        if len(remaining)<=slots:upper=value+possible
        else:
            deltas=sorted((p.weight(p.covers[v] & uncovered) for v in remaining),reverse=True)
            upper=min(inherited,value+possible,value+sum(deltas[:slots]))
        return (group,remaining,uncovered,value,upper)

    for elapsed,event in events:
        if isinstance(elapsed,bool) or not isfinite(elapsed) or elapsed<prior or elapsed<0:
            raise ValueError('invalid external bound timestamp')
        prior=elapsed
        if not isinstance(event,dict):raise ValueError('malformed bound event')
        group=instance.validate_selection(event.get('selected',[]),k)
        if event.get('kind')=='universal_v1':
            if p is not None or event.get('ops') or rational(event['upper']) != (1 if k else 0):
                raise ValueError('invalid universal bound')
            upper=Fraction(1 if k else 0)
            value=ExactCoverage(instance).score(group)
        elif event.get('kind')=='online_partition_v1':
            if p is None:
                p=_IntegerRoutes(ExactCoverage(instance),20_000)
                root=leaf((),tuple(range(len(p.oracle.nodes))),p.all_routes,0,p.scale)
                leaves={0:root};heap=[(-root[-1],0)]
            ops=event.get('ops')
            if not isinstance(ops,list) or len(ops)>50_000 or count+len(ops)>50_000:
                raise ValueError('missing or excessive split journal')
            for op in ops:
                if not isinstance(op,list) or len(op)!=2 or any(type(x) is not int for x in op):
                    raise ValueError('malformed split operation')
                parent,v=op
                if parent not in leaves:raise ValueError('missing, duplicate or closed parent')
                selected,remaining,uncovered,value,inherited=leaves.pop(parent)
                if v not in remaining or len(selected)>=k or len(remaining)<=k-len(selected):
                    raise ValueError('invalid split variable or terminal split')
                rest=tuple(x for x in remaining if x!=v)
                gain=p.weight(p.covers[v]&uncovered)
                states=[leaf(selected+(v,),rest,uncovered & ~p.covers[v],value+gain,inherited),
                        leaf(selected,rest,uncovered,value,inherited)]
                for state in states:
                    leaves[next_id]=state;heapq.heappush(heap,(-state[-1],next_id));next_id+=1
                count+=1
            if type(event.get('splits')) is not int or event['splits']!=count:
                raise ValueError('split count does not match complete journal')
            while heap and heap[0][1] not in leaves:heapq.heappop(heap)
            value=p.oracle.score(group)
            upper=Fraction(-heap[0][0],p.scale)
            if upper != rational(event['upper']):raise ValueError('claimed bound does not match partition')
        else:raise ValueError('unknown bound witness')
        if upper>previous or value>upper:raise ValueError('nonmonotone or inconsistent certificate')
        previous=upper
        certified.append({'received_seconds':elapsed,'upper_exact':str(upper),
            'feasible_coverage_exact':str(value),'quality_lower_bound_exact':str(value/upper if upper else Fraction(1)),
            'selected':list(group),'optimality_proved':value==upper,
            'partition_splits_verified':count})
    return certified
