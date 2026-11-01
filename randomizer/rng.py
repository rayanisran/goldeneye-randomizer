"""A fixed random-number generator for seeds.

Python's `random` module is not promised to give the same sequence across
Python versions, and a race needs the same seed number to produce the same
game on every machine. SplitMix64 is a few lines of integer arithmetic, so the
sequence is identical everywhere, forever.
"""

MASK = (1 << 64) - 1


class SeedRNG:
    def __init__(self, seed):
        self.state = seed & MASK

    def next64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
        return z ^ (z >> 31)

    def random(self):
        """Float in [0, 1)."""
        return (self.next64() >> 11) / float(1 << 53)

    def below(self, n):
        """Integer in [0, n), unbiased (rejection sampling)."""
        if n <= 0:
            raise ValueError("empty range")
        limit = (1 << 64) - ((1 << 64) % n)
        while True:
            v = self.next64()
            if v < limit:
                return v % n

    def randint(self, a, b):
        return a + self.below(b - a + 1)

    def choice(self, seq):
        return seq[self.below(len(seq))]

    def shuffle(self, seq):
        for i in range(len(seq) - 1, 0, -1):
            j = self.below(i + 1)
            seq[i], seq[j] = seq[j], seq[i]

    def sample(self, seq, k):
        pool = list(seq)
        self.shuffle(pool)
        return pool[:k]

    def weighted(self, seq, weights):
        """One element of seq, chosen with the given (positive) weights."""
        total = sum(weights)
        r = self.random() * total
        acc = 0.0
        for item, w in zip(seq, weights):
            acc += w
            if r < acc:
                return item
        return seq[-1]
