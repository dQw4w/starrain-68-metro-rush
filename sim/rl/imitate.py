"""Warm start: teach the network to copy the rule-based ExplorerAgent.

Evolution strategies starting from random weights spends most of its budget
rediscovering things like "claiming a free station is good" through noise.
Cloning the rule bot first means ES starts from a player that's already
roughly as good as the bot and only has to find where the bot's rules are
wrong.

Movement is cloned with a softmax over each turn's options (cross-entropy on
the option the bot picked). The claim head is set by hand to the bot's
habits — always claim at the minimum, never top up — and the call-your-shot
risk starts at 0, which is the same expected-value-maximising call the bot
makes.
"""
from __future__ import annotations

import random

import numpy as np
import torch

from agent import ExplorerAgent
from config import SimConfig
from engine import Engine
from network import Network
from rl.policy import HIDDEN, N_GLOBAL, N_OPTION, NeuralAgent, init_params, unpack


class _Recorder:
    """Plays as the rule bot, writing down (features, choice) every turn."""

    def __init__(self, rng: random.Random, featurizer: NeuralAgent, out: list):
        self.bot = ExplorerAgent(rng)
        self.feat = featurizer
        self.out = out

    def decide(self, engine, team, options):
        d = self.bot.decide(engine, team, options)
        if len(options) > 1:
            self.out.append((self.feat.features(engine, team, options), d.option_index))
        return d


def collect(games: int, seed: int = 0) -> list:
    featurizer = NeuralAgent(init_params(np.random.default_rng(0)))
    data: list = []
    for g in range(games):
        rng = random.Random(seed + g)
        cfg = SimConfig()
        agents = {name: _Recorder(rng, featurizer, data) for name in cfg.starting_chips}
        Engine(cfg, Network(cfg), agents, rng).run()
    return data


def clone(games: int = 150, epochs: int = 30, seed: int = 0) -> np.ndarray:
    data = collect(games, seed)
    torch.manual_seed(seed)
    l1 = torch.nn.Linear(N_OPTION + N_GLOBAL, HIDDEN)
    l2 = torch.nn.Linear(HIDDEN, 1, bias=False)
    opt = torch.optim.Adam(list(l1.parameters()) + list(l2.parameters()), lr=3e-3)
    xs = [torch.tensor(x, dtype=torch.float32) for x, _ in data]
    ys = [y for _, y in data]
    order = list(range(len(data)))
    rng = random.Random(seed)
    for _ in range(epochs):
        rng.shuffle(order)
        for start in range(0, len(order), 64):
            loss = 0.0
            batch = order[start:start + 64]
            for i in batch:
                logits = l2(torch.tanh(l1(xs[i]))).squeeze(-1)
                loss = loss + torch.nn.functional.cross_entropy(logits[None], torch.tensor([ys[i]]))
            opt.zero_grad()
            (loss / len(batch)).backward()
            opt.step()
    with torch.no_grad():
        acc = np.mean([int(torch.argmax(l2(torch.tanh(l1(x))).squeeze(-1))) == y for x, y in zip(xs, ys)])

    theta = np.zeros_like(init_params(np.random.default_rng(seed)))
    p = unpack(theta)
    p["w1"][:] = l1.weight.detach().numpy().T
    p["b1"][:] = l1.bias.detach().numpy()
    p["w2"][:] = l2.weight.detach().numpy()[0]
    # Claim head: frac = sigmoid(3*is_claim - 4.7) ≈ 0.15 for a claim (just
    # past the 0.1 pass line, so it pays the minimum) and ≈ 0.01 for a top-up
    # (passed) — the bot's habits exactly.
    p["claim_w"][N_GLOBAL + 0] = 3.0
    p["claim_b"][0] = -4.7
    print(f"cloned rule bot from {len(data)} decisions, {acc:.0%} agreement", flush=True)
    return theta
