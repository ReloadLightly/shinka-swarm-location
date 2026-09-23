"""Anytime DFBnB and utility-form APTS, with incremental partition witnesses.

The ordering for APTS is H/(T-V), where T is incumbent integer mass + 1,
V is partial utility, and H is an admissible additional-utility estimate. This
is the utility-tail counterpart of Stern/Puzis/Felner (2011)'s relative-error
ordering, not a calibrated probability. See docs/strong_baselines.md.
"""
from dataclasses import dataclass
from fractions import Fraction
import heapq
from time import perf_counter

from .route_search import SearchDeadline, check_time


@dataclass(frozen=True)
class State:
    selected: tuple
    remaining: tuple
    covered: int
    value: int
    upper: int
    terminal: bool


def inspect(p, k, selected, remaining, covered, value, inherited):
    slots = k-len(selected)
    if slots < 0:
        raise ValueError('cardinality exceeded')
    if slots == 0 or not remaining:
        return State(selected,remaining,covered,value,value,True)
    union = 0
    for v in remaining:
        union |= p.covers[v]
    possible = p.weight(union & ~covered)
    if len(remaining) <= slots:
        return State(selected,remaining,covered,value,value+possible,True)
    gains = p.gains(covered,remaining)
    upper = min(inherited, value+possible, value+sum(sorted((g for g,_ in gains),reverse=True)[:slots]))
    return State(selected,remaining,covered,value,upper,False)


def potential_key(value, upper, target):
    """Larger utility potential first; exact Fraction ordering and no 0/0."""
    if value >= target:
        return (0, Fraction(), -value)
    if upper < target:
        return (2, Fraction(), -value)
    return (1, -Fraction(upper-value, target-value), -value)


class PartitionSearch:
    """Search state remains a valid partition at every report/interrupt boundary.

    Leaf bounds for CLOSED as well as OPEN subtrees stay in the proof. Expansions
    are committed only after both children are constructed. Interrupted work on
    a popped node therefore cannot make a feasible subtree disappear.
    """
    def __init__(self,p,k,initial,mode='dfbnb',*,max_splits=50_000,max_open=100_000):
        if mode not in ('dfbnb','potential'):
            raise ValueError('unknown bound-guided method')
        if type(max_splits) is not int or max_splits < 0 or max_splits > 50_000:
            raise ValueError('invalid split limit')
        if type(max_open) is not int or max_open < 1 or max_open > 100_000:
            raise ValueError('invalid frontier limit')
        p.instance.validate_budget(k)
        if len(initial) > k or len(set(initial)) != len(initial) or any(type(i) is not int or not 0 <= i < len(p.nodes) for i in initial):
            raise ValueError('invalid initial group')
        self.p,self.k,self.mode=p,k,mode
        self.best_group=tuple(initial);self.best=p.score(initial)
        root=inspect(p,k,(),tuple(range(len(p.nodes))),0,0,p.scale)
        self.leaves={0:root.upper}
        self.open={0:root}
        self.stack=[0]
        self.heap=[]
        self.bound_heap=[(-root.upper,0)]
        self.ops=[];self.sent=0;self.next_id=1
        self.splits=0;self.expanded=0;self.rekeys=0
        self.max_splits=max_splits;self.max_open=max_open
        self.termination='running'
        self.peak_open=1
        if mode=='potential': self._rekey()

    def _rekey(self):
        self.heap=[(*potential_key(s.value,s.upper,self.best+1),i) for i,s in self.open.items()]
        heapq.heapify(self.heap)
        self.rekeys+=1

    def upper(self):
        while self.bound_heap and self.bound_heap[0][1] not in self.leaves:
            heapq.heappop(self.bound_heap)
        return max(self.best,-self.bound_heap[0][0]) if self.bound_heap else self.best

    def snapshot(self):
        result={'kind':'online_partition_v1','ops':self.ops[self.sent:],
                'selected':self.p.ids(self.best_group),'upper':str(Fraction(self.upper(),self.p.scale)),
                'splits':self.splits,'termination':self.termination,
                'open_nodes':len(self.open),'expanded':self.expanded,'rekeys':self.rekeys}
        self.sent=len(self.ops)
        return result

    def step(self,deadline=float('inf')):
        if not self.open:
            self.termination='exhausted';return False
        if self.splits>=self.max_splits or len(self.open)>=self.max_open:
            self.termination='resource_limit';return False
        check_time(deadline)
        i=self.stack[-1] if self.mode=='dfbnb' else self.heap[0][-1]
        state=self.open[i]  # Kept until children, bounds and all bookkeeping are ready.
        candidate=state.selected
        if state.terminal and len(candidate)+len(state.remaining)<=self.k:
            candidate+=state.remaining
        value=self.p.score(candidate)
        if value>self.best:
            self.best,self.best_group=value,candidate
            if self.mode=='potential':
                self._rekey()
                # The incumbent changed every OPEN priority. Select afresh next step.
                return True
        if state.terminal or state.upper<=self.best:
            del self.open[i]
            if self.mode=='dfbnb':self.stack.pop()
            else:heapq.heappop(self.heap)
            self.expanded+=1
            return True
        gains=self.p.gains(state.covered,state.remaining)
        _,v=min(gains,key=lambda x:(-x[0],x[1]))
        rest=tuple(x for x in state.remaining if x!=v)
        covered=state.covered | self.p.covers[v]
        a=inspect(self.p,self.k,state.selected+(v,),rest,covered,self.p.weight(covered),state.upper)
        b=inspect(self.p,self.k,state.selected,rest,state.covered,state.value,state.upper)
        check_time(deadline)  # Expensive unfinished expansion is not committed.
        del self.open[i];del self.leaves[i]
        if self.mode=='dfbnb':self.stack.pop()
        else:heapq.heappop(self.heap)
        ai,bi=self.next_id,self.next_id+1;self.next_id+=2
        for index,child in ((ai,a),(bi,b)):
            self.open[index]=child;self.leaves[index]=child.upper
            heapq.heappush(self.bound_heap,(-child.upper,index))
            if self.mode=='potential':heapq.heappush(self.heap,(*potential_key(child.value,child.upper,self.best+1),index))
        if self.mode=='dfbnb':self.stack.extend([bi,ai])
        self.ops.append([i,v]);self.splits+=1;self.expanded+=1
        self.peak_open=max(self.peak_open,len(self.open))
        return True

    def run(self,report,bound_report,deadline):
        bound_report(self.snapshot())
        previous=self.best
        try:
            while self.step(deadline):
                if self.best>previous:
                    report(self.p.ids(self.best_group));previous=self.best
                    bound_report(self.snapshot())
                elif self.splits-self.sent>=128:
                    bound_report(self.snapshot())
            bound_report(self.snapshot())
        except SearchDeadline:
            self.termination='advisory_deadline'
            bound_report(self.snapshot())
        return self.best_group
