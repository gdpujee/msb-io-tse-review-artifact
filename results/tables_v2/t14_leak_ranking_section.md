### 5.8 RQ7: Does the leak change which configuration wins?

Section 5.7 measures the leak as a score shift on a single baseline. A reader of a comparative result asks a different question: if the query rule changes, does the *ordering* of configurations change? A uniform shift would leave every comparative conclusion intact; a configuration-dependent shift would not. Both arms already exist, so this is a re-reading of released results rather than a new experiment: the same eight configurations on the same 1,791 instances, scored once under each rule (Table 8).

**Ordering.** The leading configuration is unchanged under both rules and both metrics, and the two orderings are close. By MRR, Spearman \(\rho\) = 0.9286 (repository-cluster 95% CI [0.9286, 1.0000]) and Kendall \(\tau\) = 0.8571, with 26 concordant and 2 discordant of 28 pairs; by Hit@1, \(\rho\) = 0.9762 and \(\tau\) = 0.9286 (27 of 28 pairs concordant). By MRR the positions of BM25, +pathx3, +bothcues change; by Hit@1 only BM25 and +bothcues do. Every other position is identical under the two rules.

**The flips are between indistinguishable configurations.** By Hit@1 one of the 28 pairwise differences changes sign and by MRR two do; all of them involve the combination of both cues. Under MRR, BM25 is ahead by 0.0013 under the issue-only rule and behind by 0.0051 under the superseded rule, with a paired interval of [-0.0274, +0.0506] that contains zero and a repository-level \(p\) of 0.157. Reporting this as a reversal would overstate it: the two configurations were never separated by more than a few thousandths, and they are not separated under either rule.

**The leak is not uniform.** If the shift were the same everywhere the ordering could not move at all. It is not: the combination of both cues gains +0.0233 MRR against +0.0169 for plain BM25, it is the only configuration whose Hit@1 interval [+0.0027, +0.0448] excludes zero, and it is the only configuration whose position improves under either metric. The mechanism is visible in the query text rather than inferred (Table 9). The share of instances whose query names the gold file path rises from 0.1748 to 0.1982 overall (+0.0235), with the whole rise in the leaked stratum (0.1479 to 0.1805) and no rise at all in the negative-control stratum (0.2440 to 0.2440). The leaked text therefore changes *what* the query names, not merely how long it is, and the configuration that exploits that naming most is the one whose position moves most.

**Reading.** Two conclusions follow, and the second is the more useful one. First, a leaderboard built on the superseded rule would most likely have named the same winner: the leak is not large enough to overturn a clear leader, which bounds how much damage it can have done to published rankings. Second, the leak is nevertheless a bias in the comparison and not a uniform offset, so a ranking published under one rule is not a ranking under the other, and differences of a few thousandths between adjacent configurations should not be read as real under either. With eight configurations the agreement measures are coarse: \(\tau\) moves in steps of 1/28 = 0.036, so the ordering statistic cannot resolve small changes and we do not claim it would detect them.

**Table 8.** Per-configuration means under both query rules, ordered by issue-only MRR (n = 1,791; 57 repository clusters). The interval is a repository-cluster bootstrap. Configuration labels are those of Figure 2.

| Configuration | Hit@1 issue-only | Hit@1 superseded | Δ Hit@1 | 95% CI | MRR issue-only | MRR superseded | Δ MRR |
|---|---:|---:|---:|---|---:|---:|---:|
| +pathcue | 0.4366 | 0.4511 | +0.0145 | [-0.0041, +0.0345] | 0.5673 | 0.5845 | +0.0171 |
| +pathx3 | 0.4098 | 0.4260 | +0.0162 | [-0.0027, +0.0357] | 0.5431 | 0.5607 | +0.0177 |
| BM25 | 0.4065 | 0.4210 | +0.0145 | [-0.0043, +0.0338] | 0.5405 | 0.5574 | +0.0169 |
| +bothcues | 0.4003 | 0.4243 | +0.0240 | [+0.0027, +0.0448] | 0.5392 | 0.5625 | +0.0233 |
| +symcue | 0.3629 | 0.3836 | +0.0207 | [+0.0000, +0.0431] | 0.5067 | 0.5277 | +0.0211 |
| +cues+graph | 0.3322 | 0.3439 | +0.0117 | [-0.0075, +0.0276] | 0.4731 | 0.4888 | +0.0157 |
| +pathcue+graph | 0.3116 | 0.3272 | +0.0156 | [-0.0117, +0.0375] | 0.4495 | 0.4627 | +0.0133 |
| +graph | 0.2457 | 0.2535 | +0.0078 | [-0.0145, +0.0247] | 0.3905 | 0.3967 | +0.0062 |

**Table 9.** Share of instances whose query names the gold file path, by stratum. The Python stratum serves as a negative-control stratum for query length and repetition effects (its treatment query repeats the pre-solution issue text under a synthetic header, adding no post-solution text); an increase there would indicate a query length or repetition artifact rather than genuine leakage.

| Stratum | n | issue-only | superseded | Δ |
|---|---:|---:|---:|---:|
| All | 1,791 | 0.1748 | 0.1982 | +0.0235 |
| Python (negative control) | 500 | 0.2440 | 0.2440 | 0.0000 |
| Non-Python | 1,291 | 0.1479 | 0.1805 | +0.0325 |

Figure 6 displays both orderings side by side.

![Figure 6. Rank of each configuration under the issue-only and the superseded query rules, by MRR.](../results/figures/fig6_rank_shift.png)

**Figure 6.** Rank of each configuration under the issue-only rule (left) and the superseded rule (right), by MRR. Only the positions of BM25, +pathx3, +bothcues change; the leader does not. Colours are assigned by the issue-only rank.
