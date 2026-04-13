"""
Parche opcional: barra tqdm en el bucle principal de mlx_lm.tuner.trainer.train.

Derivado de mlx_lm (Apple) — mantener alineado con la versión instalada de mlx-lm si actualizas el trainer upstream.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Optional

import mlx.core as mx
import mlx.nn as nn
import numpy as np
from mlx.nn.utils import average_gradients
from mlx.utils import tree_flatten, tree_map
from tqdm import tqdm

from mlx_lm.tuner.callbacks import TrainingCallback
from mlx_lm.tuner.datasets import CacheDataset
from mlx_lm.tuner.trainer import (
    TrainingArgs,
    default_loss,
    grad_checkpoint,
)
from mlx_lm.tuner import trainer as _trainer

_clear_cache = _trainer._clear_cache

# Un solo aviso por arranque de train (mlx upstream imprime uno por batch → validación + tqdm rotos).
_truncation_warn_emitted = False


def _reset_truncation_warning_flag() -> None:
    global _truncation_warn_emitted
    _truncation_warn_emitted = False


def _fmt_eta_hhmmss(seconds: float) -> str:
    """Formatea segundos como H:MM:SS o M:SS; devuelve '?' si no es estimable."""
    if seconds <= 0 or seconds != seconds or seconds == float("inf"):
        return "?"
    total = int(round(seconds))
    h, r = divmod(total, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def _schedules_eval_at_iter(it: int, iters: int, steps_per_eval: int, has_val: bool) -> bool:
    """Misma condición que el bucle train (evaluate antes del step)."""
    if not has_val:
        return False
    if it == 1 or it == iters:
        return True
    if steps_per_eval and steps_per_eval > 0 and it % steps_per_eval == 0:
        return True
    return False


def evaluate_without_nested_tqdm(
    model,
    dataset,
    batch_size,
    num_batches,
    max_seq_length=2048,
    loss: Callable = default_loss,
    iterate_batches: Callable = _trainer.iterate_batches,
    clear_cache_threshold: int = 0,
) -> float:
    """
    Igual que mlx_lm.tuner.trainer.evaluate pero sin tqdm interno «Calculating loss...»,
    para no mezclar líneas con la barra LoRA.
    """
    model.eval()
    all_losses = mx.array(0.0)
    ntokens = mx.array(0.0)

    index_iterator = iter(range(num_batches)) if num_batches != -1 else iter(int, 1)

    batch_iter = zip(
        index_iterator,
        iterate_batches(
            dataset=dataset,
            batch_size=batch_size,
            max_seq_length=max_seq_length,
            comm_group=mx.distributed.init(),
        ),
    )

    for _, batch in batch_iter:
        losses, toks = loss(model, *batch)
        all_losses += losses * toks
        ntokens += toks
        mx.eval(all_losses, ntokens)
        _clear_cache(clear_cache_threshold)

    all_losses = mx.distributed.all_sum(all_losses, stream=mx.cpu)
    ntokens = mx.distributed.all_sum(ntokens, stream=mx.cpu)
    avg_loss = (all_losses / ntokens).item()

    return avg_loss


def _count_eval_runs_after(
    after_it: int, iters: int, steps_per_eval: int, has_val: bool
) -> int:
    """Cuántas validaciones quedan en iteraciones (after_it, iters]."""
    if not has_val:
        return 0
    return sum(
        1
        for j in range(after_it + 1, iters + 1)
        if _schedules_eval_at_iter(j, iters, steps_per_eval, True)
    )


def iterate_batches_trunc_warn_once(
    dataset,
    batch_size,
    max_seq_length,
    loop=False,
    seed=None,
    comm_group=None,
):
    """Igual que mlx_lm.tuner.trainer.iterate_batches pero sin spamear WARNING por batch."""
    global _truncation_warn_emitted

    if isinstance(dataset, CacheDataset):
        len_fn = lambda idx: dataset.itemlen(idx)
    else:
        len_fn = lambda idx: len(dataset[idx][0])
    idx = sorted(range(len(dataset)), key=len_fn)
    if len(dataset) < batch_size:
        raise ValueError(
            f"Dataset must have at least batch_size={batch_size}"
            f" examples but only has {len(dataset)}."
        )

    if comm_group is not None:
        offset = comm_group.rank()
        step = comm_group.size()
    else:
        offset = 0
        step = 1
    if batch_size % step != 0:
        raise ValueError("The batch size must be divisible by the number of workers")

    batch_idx = [
        idx[i + offset : i + offset + batch_size : step]
        for i in range(0, len(idx) - batch_size + 1, batch_size)
    ]
    if seed:
        np.random.seed(seed)
    while True:
        indices = np.random.permutation(len(batch_idx))
        for i in indices:
            batch = [dataset[j] for j in batch_idx[i]]
            if len(batch[0]) == 2:
                batch, offsets = zip(*batch)
            else:
                offsets = [0] * len(batch)
            lengths = [len(x) for x in batch]
            if max(lengths) > max_seq_length:
                if not _truncation_warn_emitted:
                    tqdm.write(
                        f"[WARNING] Some sequences are longer than {max_seq_length} tokens. "
                        f"(example longest {max(lengths)} → truncated). "
                        "Further per-batch truncation messages are suppressed this run. "
                        "Consider pre-splitting your data to save memory.",
                    )
                    _truncation_warn_emitted = True

            pad_to = 32
            max_length_in_batch = 1 + pad_to * ((max(lengths) + pad_to - 1) // pad_to)
            max_length_in_batch = min(max_length_in_batch, max_seq_length)

            batch_arr = np.zeros((batch_size // step, max_length_in_batch), np.int32)

            for j in range(batch_size // step):
                truncated_length = min(lengths[j], max_seq_length)
                batch_arr[j, :truncated_length] = batch[j][:truncated_length]
                lengths[j] = truncated_length

            batch = mx.array(batch_arr)
            yield batch, mx.array(list(zip(offsets, lengths)))

        if not loop:
            break


def train_with_tqdm(
    model,
    optimizer,
    train_dataset,
    val_dataset=None,
    args: TrainingArgs = TrainingArgs(),
    loss: callable = default_loss,
    iterate_batches: Optional[Callable] = None,
    training_callback: TrainingCallback = None,
):
    _reset_truncation_warning_flag()
    ib_fn = iterate_batches if iterate_batches is not None else _trainer.iterate_batches

    if mx.metal.is_available():
        mx.set_wired_limit(mx.device_info()["max_recommended_working_set_size"])
    print(f"Starting training..., iters: {args.iters}")
    world = mx.distributed.init()
    world_size = world.size()
    rank = world.rank()
    if world_size > 1:
        print(f"Node {rank} of {world_size}")

    if args.grad_checkpoint:
        grad_checkpoint(model.layers[0])

    loss_value_and_grad = nn.value_and_grad(model, loss)

    grad_accum_steps = args.grad_accumulation_steps
    if grad_accum_steps < 1:
        raise ValueError("grad_accumulation_steps must be at least 1")

    state = [model.state, optimizer.state, mx.random.state]

    @partial(mx.compile, inputs=state, outputs=state)
    def step(batch, prev_grad, do_update):
        (lvalue, toks), grad = loss_value_and_grad(model, *batch)

        if prev_grad is not None:
            grad = tree_map(lambda x, y: x + y, grad, prev_grad)

        if do_update:
            grad = average_gradients(grad)
            if grad_accum_steps > 1:
                grad = tree_map(lambda x: x / grad_accum_steps, grad)
            optimizer.update(model, grad)
            grad = None

        return lvalue, toks, grad

    model.train()
    losses = 0
    n_tokens = 0
    steps = 0
    trained_tokens = 0
    train_time = 0
    grad_accum = None

    batch_iter = zip(
        range(1, args.iters + 1),
        ib_fn(
            dataset=train_dataset,
            batch_size=args.batch_size,
            max_seq_length=args.max_seq_length,
            loop=True,
            comm_group=world,
        ),
    )
    # Manual tqdm (sin envolver el iterable): n solo sube al terminar cada iteración.
    # ETA fin: EMA del tiempo de train (sin val) × iteraciones restantes + EMA(val) × validaciones
    # programadas restantes (la iteración 1 suele incluir val largo; no mezclar con el resto).
    pbar = tqdm(
        total=args.iters,
        desc="LoRA",
        unit="it",
        dynamic_ncols=True,
        disable=(rank != 0),
        smoothing=0.08,
        mininterval=0.04,
        maxinterval=0.25,
        bar_format=(
            "{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} "
            "| {elapsed} transcurrido{postfix} | {rate_fmt}"
        ),
    )
    _ema_train_sec: float | None = None
    _ema_val_sec: float | None = None
    _postfix_fin = "?"
    _train_pf: dict[str, str] = {}
    if rank == 0:
        pbar.set_postfix(fin=_postfix_fin, refresh=False)

    # Durante evaluate() / pasos largos sin update(), tqdm no redibuja: elapsed y ETA se congelan.
    # Un heartbeat refresca la línea de tiempos en segundo plano (solo rank 0).
    _hb_stop: threading.Event | None = None
    _hb_thread: threading.Thread | None = None
    if rank == 0:
        _hb_stop = threading.Event()

        def _pbar_time_heartbeat() -> None:
            while not _hb_stop.wait(0.2):
                try:
                    pbar.refresh()
                except OSError:
                    break

        _hb_thread = threading.Thread(
            target=_pbar_time_heartbeat,
            daemon=True,
            name="duckclaw-pbar-time-heartbeat",
        )
        _hb_thread.start()
        # #region agent log
        try:
            with open(
                "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-5e21eb.log",
                "a",
                encoding="utf-8",
            ) as _dbg:
                _dbg.write(
                    json.dumps(
                        {
                            "sessionId": "5e21eb",
                            "hypothesisId": "H2",
                            "location": "mlx_train_tqdm_patch.py:heartbeat",
                            "message": "time_heartbeat_started",
                            "data": {"interval_s": 0.2},
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except OSError:
            pass
        # #endregion

    try:
        for it, batch in batch_iter:
            iter_start = time.perf_counter()
            val_time_this_iter = 0.0
            has_val = val_dataset is not None
            spe = getattr(args, "steps_per_eval", 0) or 0
            if rank == 0 and _ema_train_sec is not None:
                rem_iters = args.iters - it + 1
                n_val = _count_eval_runs_after(it - 1, args.iters, spe, has_val)
                v = _ema_val_sec or 0.0
                eta_sec = _ema_train_sec * rem_iters + v * n_val
                _postfix_fin = _fmt_eta_hhmmss(eta_sec)
                pbar.set_postfix(fin=_postfix_fin, **_train_pf, refresh=True)
            tic = time.perf_counter()
            if val_dataset and _schedules_eval_at_iter(it, args.iters, spe, True):
                tic = time.perf_counter()
                val_loss = evaluate_without_nested_tqdm(
                    model=model,
                    dataset=val_dataset,
                    loss=loss,
                    batch_size=args.batch_size,
                    num_batches=args.val_batches,
                    max_seq_length=args.max_seq_length,
                    iterate_batches=ib_fn,
                    clear_cache_threshold=args.clear_cache_threshold,
                )
                model.train()
                val_time = time.perf_counter() - tic
                val_time_this_iter = val_time
                if rank == 0:
                    tqdm.write(
                        f"Iter {it}: Val loss {val_loss:.3f}, "
                        f"Val took {val_time:.3f}s"
                    )

                if training_callback is not None:
                    val_info = {
                        "iteration": it - 1,
                        "val_loss": val_loss,
                        "val_time": val_time,
                    }
                    training_callback.on_val_loss_report(val_info)

                tic = time.perf_counter()

            lvalue, toks, grad_accum = step(
                batch,
                grad_accum,
                it % grad_accum_steps == 0,
            )

            losses += lvalue
            n_tokens += toks
            steps += 1
            mx.eval(state, losses, n_tokens, grad_accum)
            _clear_cache(args.clear_cache_threshold)
            train_time += time.perf_counter() - tic

            if it % args.steps_per_report == 0 or it == args.iters:
                train_loss = mx.distributed.all_sum(losses, stream=mx.cpu).item()
                train_loss /= steps * world_size
                n_tokens = mx.distributed.all_sum(n_tokens, stream=mx.cpu).item()
                learning_rate = optimizer.learning_rate.item()
                it_sec = args.steps_per_report / train_time if train_time > 0 else 0.0
                tokens_sec = float(n_tokens) / train_time if train_time > 0 else 0.0
                trained_tokens += n_tokens
                peak_mem = mx.get_peak_memory() / 1e9
                if rank == 0:
                    _train_pf = {
                        "loss": f"{train_loss:.3f}",
                        "tok_s": f"{tokens_sec:.0f}",
                        "mem_GB": f"{peak_mem:.2f}",
                    }
                    print(
                        f"Iter {it}: Train loss {train_loss:.3f}, "
                        f"Learning Rate {learning_rate:.3e}, "
                        f"It/sec {it_sec:.3f}, "
                        f"Tokens/sec {tokens_sec:.3f}, "
                        f"Trained Tokens {trained_tokens}, "
                        f"Peak mem {peak_mem:.3f} GB",
                        flush=True,
                    )

                if training_callback is not None:
                    train_info = {
                        "iteration": it,
                        "train_loss": train_loss,
                        "learning_rate": learning_rate,
                        "iterations_per_second": it_sec,
                        "tokens_per_second": tokens_sec,
                        "trained_tokens": trained_tokens,
                        "peak_memory": peak_mem,
                    }
                    training_callback.on_train_loss_report(train_info)

                losses = 0
                n_tokens = 0
                steps = 0
                train_time = 0

            if it % args.steps_per_save == 0 and rank == 0:
                adapter_weights = dict(tree_flatten(model.trainable_parameters()))
                mx.save_safetensors(str(args.adapter_file), adapter_weights)
                checkpoint = (
                    Path(args.adapter_file).parent / f"{it:07d}_adapters.safetensors"
                )
                mx.save_safetensors(str(checkpoint), adapter_weights)
                tqdm.write(
                    f"Iter {it}: Saved adapter weights to "
                    f"{args.adapter_file} and {checkpoint}."
                )

            if rank == 0:
                _iter_dur = time.perf_counter() - iter_start
                train_only = max(_iter_dur - val_time_this_iter, 1e-6)
                if _ema_train_sec is None:
                    _ema_train_sec = train_only
                else:
                    _ema_train_sec = 0.1 * train_only + 0.9 * _ema_train_sec
                if val_time_this_iter > 0:
                    if _ema_val_sec is None:
                        _ema_val_sec = val_time_this_iter
                    else:
                        _ema_val_sec = 0.2 * val_time_this_iter + 0.8 * _ema_val_sec
                _rem = args.iters - it
                n_val_rem = _count_eval_runs_after(it, args.iters, spe, has_val)
                vsec = _ema_val_sec or 0.0
                eta_sec = (
                    0.0
                    if _rem <= 0
                    else _ema_train_sec * _rem + vsec * n_val_rem
                )
                _postfix_fin = "0:00" if _rem <= 0 else _fmt_eta_hhmmss(eta_sec)
                pbar.update(1)
                pbar.set_postfix(fin=_postfix_fin, **_train_pf, refresh=True)
                # #region agent log
                if it <= 3:
                    try:
                        with open(
                            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-5e21eb.log",
                            "a",
                            encoding="utf-8",
                        ) as _dbg:
                            _dbg.write(
                                json.dumps(
                                    {
                                        "sessionId": "5e21eb",
                                        "hypothesisId": "H1",
                                        "location": "mlx_train_tqdm_patch.py:iter_end",
                                        "message": "pbar_after_iter_done",
                                        "data": {
                                            "it": it,
                                            "pbar_n": getattr(pbar, "n", None),
                                            "fin": _postfix_fin,
                                            "ema_train_s": _ema_train_sec,
                                            "ema_val_s": _ema_val_sec,
                                            "n_val_rem": n_val_rem,
                                            "eta_s": eta_sec,
                                        },
                                        "timestamp": int(time.time() * 1000),
                                    }
                                )
                                + "\n"
                            )
                    except OSError:
                        pass
                # #endregion

    finally:
        if _hb_stop is not None:
            _hb_stop.set()
        if _hb_thread is not None:
            _hb_thread.join(timeout=3.0)

    if rank == 0:
        pbar.close()

    if rank == 0:
        adapter_weights = dict(tree_flatten(model.trainable_parameters()))
        mx.save_safetensors(str(args.adapter_file), adapter_weights)
        print(f"Saved final weights to {args.adapter_file}.")


def apply_mlx_train_tqdm_patch() -> None:
    """Sustituye trainer.train antes de importar/ejecutar mlx_lm.lora.main."""
    if getattr(_trainer.train, "_duckops_tqdm_patch", False):
        return
    train_with_tqdm._duckops_tqdm_patch = True  # type: ignore[attr-defined]
    _trainer.train = train_with_tqdm  # noqa: SLF001
    _trainer.iterate_batches = iterate_batches_trunc_warn_once  # noqa: SLF001

