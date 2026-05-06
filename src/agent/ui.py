from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from agent.settings import build_agent_input, load_default_params
from agent.workflow import LensResearchAgent


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOST = "127.0.0.1"
PORT = 8000


HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LensBot Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #f7f7f2;
      --panel: rgba(255, 255, 255, 0.9);
      --panel-strong: #ffffff;
      --line: rgba(15, 23, 42, 0.10);
      --line-strong: rgba(15, 23, 42, 0.18);
      --text: #111827;
      --muted: #6b7280;
      --accent: #111827;
      --green: #16a34a;
      --red: #dc2626;
      --shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
      --radius-xl: 16px;
      --radius-lg: 16px;
      --radius-md: 12px;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font-family: "Inter", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(17, 24, 39, 0.03), transparent 24%),
        linear-gradient(180deg, #fafaf8 0%, #f5f5f1 100%);
      min-height: 100vh;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
      background-size: 40px 40px;
      mask-image: linear-gradient(180deg, rgba(0,0,0,.08), transparent 72%);
    }

    .shell {
      max-width: 1680px;
      margin: 0 auto;
      padding: 78px 24px 40px;
    }

    .topbar {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      z-index: 100;
      display: flex;
      align-items: center;
      justify-content: flex-start;
      gap: 14px;
      width: 100%;
      margin: 0;
      min-height: 62px;
      padding: 10px 24px;
      border: 1px solid rgba(15, 23, 42, 0.10);
      border-left: 0;
      border-right: 0;
      border-top: 0;
      border-radius: 0;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.96));
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
      backdrop-filter: none;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .mark {
      width: 40px;
      height: 40px;
      border: 1px solid rgba(15, 23, 42, 0.08);
      border-radius: 12px;
      display: grid;
      place-items: center;
      font-weight: 700;
      letter-spacing: 0.04em;
      background: #111827;
      color: #ffffff;
    }

    .brand h1, .brand p { margin: 0; }
    .brand h1 {
      font-size: 1.48rem;
      font-weight: 800;
      letter-spacing: -0.04em;
      color: #111827;
      line-height: 1;
    }

    .topbar-desc {
      color: #4b5563;
      font-size: 0.84rem;
      line-height: 1.2;
      white-space: nowrap;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.85);
      color: var(--muted);
      font-size: 0.82rem;
    }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 0 5px rgba(22, 163, 74, 0.12);
    }

    .dot.is-running {
      background: #f59e0b;
      box-shadow: 0 0 0 5px rgba(245, 158, 11, 0.14);
    }

    .dot.is-error {
      background: var(--red);
      box-shadow: 0 0 0 5px rgba(220, 38, 38, 0.14);
    }

    .card {
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }

    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 18px;
      padding: 4px 2px 0;
    }

    .toolbar h2 {
      margin: 0;
      font-size: 0.92rem;
      font-weight: 600;
      letter-spacing: 0;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(300px, 3fr) minmax(0, 7fr);
      gap: 22px;
    }

    .panel {
      padding: 22px;
    }

    .panel h2, .section-title {
      margin: 0 0 14px;
      font-size: 1rem;
      letter-spacing: 0.02em;
    }

    .panel h3 {
      margin: 18px 0 10px;
      font-size: 0.9rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .stack { display: grid; gap: 12px; }
    .row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .triple { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }

    label {
      display: block;
      margin: 0 0 8px;
      color: #94a3b8;
      font-size: 0.88rem;
      font-weight: 600;
    }
    .stage-tag {
      margin: 8px 0 10px 0;
      color: #94a3b8;
      font-size: 0.88rem;
      font-weight: 600;
    }
    .stage-group label {
      color: var(--muted);
      font-size: 0.75rem;
      font-weight: 500;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      background: #ffffff;
      color: var(--text);
      padding: 12px 14px;
      font: inherit;
      outline: none;
      transition: border-color .18s ease, transform .18s ease;
      box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.03);
    }

    input:focus, textarea:focus, select:focus {
      border-color: rgba(17, 24, 39, 0.24);
      box-shadow: 0 0 0 4px rgba(15, 23, 42, 0.05);
      transform: translateY(-1px);
    }

    input::placeholder, textarea::placeholder {
      color: #9ca3af;
    }

    textarea {
      min-height: 130px;
      resize: vertical;
      line-height: 1.65;
    }

    .toggle {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      padding: 3px;
      gap: 4px;
      border-radius: 20px;
      background: rgba(15, 23, 42, 0.04);
      border: 1px solid rgba(15, 23, 42, 0.08);
      box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.04);
    }

    .toggle button {
      border: 1px solid transparent;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.78);
      padding: 12px 14px;
      border-radius: 18px;
      cursor: pointer;
      font: inherit;
      font-weight: 600;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
      transition: background .18s ease, border-color .18s ease, color .18s ease, transform .18s ease;
    }

    .toggle button:hover {
      border-color: rgba(15, 23, 42, 0.12);
      color: var(--text);
    }

    .toggle button.active {
      background: #111827;
      color: #ffffff;
      border-color: #111827;
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.06),
        0 1px 2px rgba(15, 23, 42, 0.10);
    }

    .check {
      display: flex;
      align-items: center;
      gap: 10px;
      color: #4b5563;
      font-size: 0.88rem;
    }

    .check input {
      width: 18px;
      height: 18px;
      accent-color: #111827;
      box-shadow: none;
    }

    .cta {
      margin-top: 20px;
      display: flex;
      gap: 12px;
    }

    .cta button {
      border: 0;
      border-radius: var(--radius-lg);
      padding: 14px 18px;
      font: inherit;
      cursor: pointer;
    }

    .primary {
      flex: 1;
      font-weight: 600;
      color: #ffffff;
      background: #111827;
      box-shadow: none;
    }

    .secondary {
      color: var(--text);
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--line);
    }

    .workspace {
      display: grid;
      gap: 20px;
    }

    .sidebar {
      position: static;
      align-self: start;
      display: grid;
      gap: 18px;
    }

    .control-card {
      background:
        linear-gradient(180deg, rgba(255,255,255,0.96), rgba(250,250,248,0.94));
    }

    .control-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 18px;
    }

    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(15, 23, 42, 0.08);
      background: rgba(17, 24, 39, 0.04);
      color: #475569;
      font-size: 0.76rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .control-head h2 {
      margin: 10px 0 4px;
      font-size: 1.28rem;
      line-height: 1.1;
    }

    .control-head p {
      margin: 0;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.55;
    }

    .control-meta {
      white-space: nowrap;
      align-self: center;
    }

    .section-block {
      display: grid;
      gap: 14px;
      padding-top: 16px;
      border-top: 1px solid rgba(15, 23, 42, 0.08);
    }

    .section-label {
      margin: 0;
      color: #64748b;
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }

    .budget-grid {
      display: grid;
      gap: 14px;
    }

    .budget-group {
      display: grid;
      gap: 10px;
      padding: 14px;
      border: 1px solid rgba(15, 23, 42, 0.08);
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
    }

    .stage-tag {
      margin: 0;
      color: #475569;
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .workspace-hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: start;
      padding: 24px 26px;
      border-radius: var(--radius-xl);
      border: 1px solid rgba(15, 23, 42, 0.08);
      background:
        radial-gradient(circle at top right, rgba(22, 163, 74, 0.08), transparent 28%),
        linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.92));
      box-shadow: var(--shadow);
    }

    .hero-copy {
      display: grid;
      gap: 14px;
    }

    .hero-meta {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .hero-heading {
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
    }

    .hero-kicker {
      color: #64748b;
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    .hero-title {
      margin: 0;
      font-size: 1.42rem;
      line-height: 1.2;
    }

    .status-copy {
      margin: 0;
      color: #475569;
      line-height: 1.8;
      max-width: 78ch;
    }

    .status-state {
      white-space: nowrap;
      padding: 12px 15px;
      border-radius: 999px;
      background: rgba(22, 163, 74, 0.10);
      color: var(--green);
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .status-state.is-idle {
      background: rgba(148, 163, 184, 0.16);
      color: #475569;
    }

    .status-state.is-running {
      background: rgba(245, 158, 11, 0.14);
      color: #b45309;
    }

    .status-state.is-error {
      background: rgba(220, 38, 38, 0.12);
      color: var(--red);
    }

    .run-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(15, 23, 42, 0.08);
      background: rgba(255,255,255,0.82);
      color: #64748b;
      font-size: 0.8rem;
    }

    .elapsed-pill {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(15, 23, 42, 0.08);
      background: #ffffff;
      color: #475569;
      font-size: 0.82rem;
      font-weight: 600;
      box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
    }

    .elapsed-pill strong {
      color: #111827;
      font-size: 1rem;
      letter-spacing: 0.04em;
    }

    .overview-grid {
      display: grid;
      grid-template-columns: minmax(260px, 0.9fr) minmax(0, 1.1fr);
      gap: 20px;
      align-items: start;
    }

    .stage-card {
      padding: 20px;
      border-radius: var(--radius-xl);
      border: 1px solid rgba(15, 23, 42, 0.08);
      background: rgba(255,255,255,0.9);
      box-shadow: var(--shadow);
    }

    .console {
      display: flex;
      flex-direction: column;
      padding: 18px;
      min-height: 0;
      height: clamp(220px, 28vh, 340px);
      background: rgba(250, 250, 248, 0.98);
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      overflow: hidden;
    }

    .console-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid rgba(15, 23, 42, 0.08);
    }

    .console-title { margin: 0; font-size: 0.96rem; letter-spacing: 0.02em; }
    .trace-card { padding: 0; overflow: hidden; }
    .trace-card .console {
      border: 0;
      border-radius: var(--radius-xl);
      background: rgba(250, 250, 248, 0.96);
    }
    .mono, pre, code { font-family: "IBM Plex Mono", monospace; }

    #timeline {
      flex: 1;
      margin: 0;
      padding: 2px 4px 2px 0;
      list-style: none;
      display: grid;
      align-content: start;
      gap: 8px;
      overflow: auto;
    }

    #timeline li {
      padding: 10px 12px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(15, 23, 42, 0.08);
      background: #ffffff;
      color: #1f2937;
      line-height: 1.52;
      font-size: 0.9rem;
      word-break: break-word;
    }

    .summary {
      margin: 0;
      color: #1f2937;
      line-height: 1.7;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      align-items: start;
    }

    .metric-column {
      min-width: 0;
      display: grid;
      gap: 10px;
    }

    .metric-source {
      margin: 0;
      color: var(--ink);
      font-size: 0.92rem;
      font-weight: 800;
      letter-spacing: 0.02em;
    }

    .metric-grid {
      display: grid;
      gap: 0;
      border-top: 1px solid var(--line);
    }

    .metric {
      min-height: 54px;
      padding: 10px 0;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      border-bottom: 1px solid var(--line);
    }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .metric strong {
      display: block;
      font-size: 1.02rem;
      text-align: right;
      word-break: break-word;
    }

    .list-card {
      display: grid;
      gap: 10px;
      max-height: 250px;
      overflow: auto;
    }

    #artifacts {
      max-height: none;
      overflow: visible;
    }

    .list-item {
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      background: #ffffff;
    }

    .list-item h4, .list-item p { margin: 0; }
    .list-item h4 { font-size: 0.9rem; }
    .list-item p { margin-top: 8px; color: var(--muted); line-height: 1.55; }
    .empty {
      color: var(--muted);
      padding: 16px;
      border: 1px dashed var(--line-strong);
      border-radius: 14px;
      text-align: center;
    }

    .insight-stack {
      display: grid;
      gap: 20px;
      align-content: start;
    }

    .result-gallery {
      display: grid;
      gap: 16px;
    }

    .result-strip {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .zemax-strip {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .result-section-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 4px 0 -4px;
    }

    .result-section-title h3 {
      margin: 0;
      color: #111827;
      font-size: 0.96rem;
      letter-spacing: 0;
      text-transform: none;
    }

    .result-section-title span {
      color: var(--muted);
      font-size: 0.78rem;
    }

    .result-panel {
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.94));
      overflow: hidden;
    }

    .result-panel.small {
      min-height: 210px;
    }

    .result-panel.large {
      min-height: 320px;
    }

    .result-panel.zemax {
      min-height: 260px;
    }

    .result-panel.zemax-wide {
      grid-column: 1 / -1;
    }

    .result-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 14px 0;
    }

    .result-head h4,
    .result-head p {
      margin: 0;
    }

    .result-head h4 {
      font-size: 0.94rem;
    }

    .result-head p {
      margin-top: 4px;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.5;
    }

    .result-image-wrap {
      padding: 12px 14px 14px;
    }

    .result-image {
      display: block;
      width: 100%;
      border-radius: var(--radius-md);
      border: 1px solid rgba(15, 23, 42, 0.08);
      background:
        linear-gradient(135deg, rgba(148, 163, 184, 0.08), rgba(255,255,255,0.95)),
        repeating-linear-gradient(45deg, rgba(148, 163, 184, 0.06) 0 10px, transparent 10px 20px);
      object-fit: cover;
      object-position: center;
    }

    .result-panel.small .result-image {
      aspect-ratio: 4 / 3;
    }

    .result-panel.large .result-image {
      aspect-ratio: 16 / 10;
      max-height: 520px;
      object-fit: contain;
      background:
        linear-gradient(180deg, rgba(248,250,252,0.98), rgba(255,255,255,0.98));
    }

    .result-panel.zemax .result-image {
      aspect-ratio: 4 / 3;
      object-fit: contain;
      background:
        linear-gradient(180deg, rgba(248,250,252,0.98), rgba(255,255,255,0.98));
    }

    .result-panel.zemax-wide .result-image {
      aspect-ratio: 16 / 7;
    }

    .result-missing {
      min-height: 160px;
      display: grid;
      place-items: center;
      padding: 18px;
      color: var(--muted);
      text-align: center;
      line-height: 1.6;
      border: 1px dashed var(--line-strong);
      border-radius: var(--radius-md);
      background: rgba(255,255,255,0.8);
    }

    .result-params {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
    }

    .param-chip {
      padding: 12px 14px;
      border-radius: var(--radius-md);
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.92);
    }

    .param-chip span {
      display: block;
      color: var(--muted);
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .param-chip strong {
      display: block;
      margin-top: 8px;
      font-size: 1rem;
      color: var(--text);
      word-break: break-word;
    }

    .file-meta {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }

    .file-path {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.5;
      word-break: break-all;
    }

    .file-link {
      color: #0f172a;
      text-decoration: none;
      border-bottom: 1px solid rgba(15, 23, 42, 0.14);
    }

    .file-link:hover {
      color: #2563eb;
      border-bottom-color: rgba(37, 99, 235, 0.35);
    }

    .sources-list {
      max-height: 300px;
    }

    .footer-note {
      display: none;
    }

    @media (max-width: 1180px) {
      .layout,
      .overview-grid,
      .triple,
      .row,
      .metrics,
      .result-strip,
      .zemax-strip,
      .result-params,
      .workspace-hero {
        grid-template-columns: 1fr;
      }

      .hero-heading {
        flex-direction: column;
        align-items: flex-start;
      }

      .sidebar {
        position: static;
      }

      .shell {
        padding: 74px 14px 28px;
      }

      .topbar {
        min-height: 58px;
        padding: 10px 14px;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar card">
      <div class="brand">
        <div class="mark">LB</div>
        <div>
          <h1>LensBot</h1>
        </div>
      </div>
      <div class="topbar-desc">自动镜头设计智能体</div>
    </div>

    <main class="layout">
      <aside class="sidebar">
        <section class="card panel control-card">
          <div class="control-head">
            <div>
              <div class="eyebrow">Lens Setup</div>
            </div>
            <div class="pill mono control-meta">deepseek-chat</div>
          </div>

          <div class="section-block">
            <p class="section-label">输入模式</p>
            <div class="toggle" id="mode-toggle">
              <button type="button" data-mode="自然语言输入" class="active">自然语言输入</button>
              <button type="button" data-mode="目标参数输入">目标参数输入</button>
            </div>
          </div>

          <div class="section-block">
            <p class="section-label">任务输入</p>
            <div id="nl-block">
              <label for="nl_prompt">任务描述</label>
              <textarea id="nl_prompt">我需要一个 52mm 焦距、F/2.9、43 度视场的镜头。</textarea>
            </div>

            <div id="param-block" style="display:none;">
              <div class="triple">
                <div>
                  <label for="foclen">焦距 (mm)</label>
                  <input id="foclen" type="number" step="0.1">
                </div>
                <div>
                  <label for="fov">视场 (deg)</label>
                  <input id="fov" type="number" step="0.1">
                </div>
                <div>
                  <label for="fnum">F 数</label>
                  <input id="fnum" type="number" step="0.1">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="bfl">后焦距 (mm)</label>
                  <input id="bfl" type="number" step="0.1">
                </div>
                <div>
                  <label for="thickness">总厚度 (mm)</label>
                  <input id="thickness" type="number" step="0.1">
                </div>
              </div>
            </div>
          </div>

          <div class="section-block">
            <p class="section-label">Optimization Budget</p>
            <div class="budget-grid">
              <div class="budget-group">
                <h4 class="stage-tag">课程学习</h4>
                <div class="triple stage-group">
                  <div>
                    <label for="iterations">迭代轮数</label>
                    <input id="iterations" type="number" step="1" min="1" value="3000">
                  </div>
                  <div>
                    <label for="spp">采样数</label>
                    <input id="spp" type="number" step="1" min="1">
                  </div>
                  <div>
                    <label for="test_per_iter">测试间隔</label>
                    <input id="test_per_iter" type="number" step="1" min="1">
                  </div>
                </div>
              </div>

              <div class="budget-group">
                <h4 class="stage-tag">微调</h4>
                <div class="triple stage-group">
                  <div>
                    <label for="fine_tune_iterations">微调轮次</label>
                    <input id="fine_tune_iterations" type="number" step="1" min="1" value="2000">
                  </div>
                  <div>
                    <label for="fine_tune_spp">微调采样数</label>
                    <input id="fine_tune_spp" type="number" step="1" min="1">
                  </div>
                  <div>
                    <label for="fine_tune_test_per_iter">微调测试间隔</label>
                    <input id="fine_tune_test_per_iter" type="number" step="1" min="1">
                  </div>
                </div>
              </div>
            </div>

            <div class="cta">
              <button class="primary" id="run-btn" type="button">Run LensBot</button>
              <button class="secondary" id="reset-btn" type="button">Reset View</button>
            </div>
          </div>
        </section>
      </aside>

      <section class="workspace">
        <section class="workspace-hero">
          <div class="hero-copy">
            <div class="hero-meta">
              <span class="hero-kicker">Design Status</span>
            </div>
            <div class="hero-heading">
              <h2 class="hero-title">镜头设计结果</h2>
              <span class="elapsed-pill mono">设计总用时 <strong id="elapsed-pill">00:00</strong></span>
            </div>
            <p class="status-copy" id="status-copy">等待新的设计任务。</p>
          </div>
          <div class="status-state" id="status-state">空闲</div>
        </section>

        <section class="stage-card trace-card">
          <div class="console">
            <div class="console-head">
              <h3 class="console-title">Trace</h3>
            </div>
            <ul id="timeline">
              <li>LensBot 已就绪。</li>
            </ul>
          </div>
        </section>

        <section class="stage-card">
          <div class="toolbar">
            <h2>Design Gallery</h2>
            <div class="pill"><span class="dot"></span><span>Results</span></div>
          </div>
          <div id="artifacts">
            <div class="empty">Artifacts appear here after design execution.</div>
          </div>
        </section>

        <section class="overview-grid">
          <div class="insight-stack">
            <section class="stage-card">
              <div class="toolbar">
                <h2>Metrics</h2>
              </div>
              <div class="metrics" id="metrics">
                <div class="empty">Run the agent to populate IQA metrics.</div>
              </div>
            </section>

            <section class="stage-card">
              <div class="toolbar">
                <h2>Sources</h2>
              </div>
              <div class="list-card sources-list" id="references">
                <div class="empty">Case references will appear here.</div>
              </div>
            </section>
          </div>

          <div class="insight-stack">
            <section class="stage-card">
              <div class="toolbar">
                <h2>Files</h2>
              </div>
              <div class="file-meta" id="file-meta">
                <div class="empty">Result files will appear here after design execution.</div>
              </div>
            </section>
          </div>
        </section>
      </section>
    </main>
  </div>

  <script>
    const defaults = __DEFAULTS__;
    let currentMode = "自然语言输入";
    let currentSource = null;
    let runStartTime = null;
    let elapsedTimer = null;

    const modeButtons = [...document.querySelectorAll("#mode-toggle button")];
    const nlBlock = document.getElementById("nl-block");
    const paramBlock = document.getElementById("param-block");
    const runBtn = document.getElementById("run-btn");
    const resetBtn = document.getElementById("reset-btn");
    const statusCopy = document.getElementById("status-copy");
    const statusState = document.getElementById("status-state");
    const elapsedPill = document.getElementById("elapsed-pill");
    const timeline = document.getElementById("timeline");
    const metrics = document.getElementById("metrics");
    const artifacts = document.getElementById("artifacts");
    const references = document.getElementById("references");
    const fileMeta = document.getElementById("file-meta");

    function setMode(mode) {
      currentMode = mode;
      modeButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.mode === mode);
      });
      nlBlock.style.display = mode === "自然语言输入" ? "block" : "none";
      paramBlock.style.display = mode === "自然语言输入" ? "none" : "block";
    }

    function setStatus(label, detail) {
      const stateKey = String(label || "").toUpperCase();
      statusState.textContent = stateKey;
      statusCopy.textContent = detail;
      statusState.classList.remove("is-idle", "is-running", "is-error");
      if (stateKey === "IDLE" || label === "空闲") {
        statusState.classList.add("is-idle");
        return;
      }
      if (stateKey === "RUNNING" || label === "运行中") {
        statusState.classList.add("is-running");
        return;
      }
      if (stateKey === "ERROR" || label === "失败") {
        statusState.classList.add("is-error");
      }
    }

    function escapeHtml(text) {
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function formatElapsed(ms) {
      const totalSeconds = Math.max(0, Math.floor(ms / 1000));
      const hours = Math.floor(totalSeconds / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      if (hours > 0) {
        return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
      }
      return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }

    function stopElapsedTimer() {
      if (elapsedTimer) {
        clearInterval(elapsedTimer);
        elapsedTimer = null;
      }
    }

    function refreshElapsed() {
      if (!runStartTime) {
        elapsedPill.textContent = "00:00";
        return;
      }
      elapsedPill.textContent = formatElapsed(Date.now() - runStartTime);
    }

    function startElapsedTimer() {
      runStartTime = Date.now();
      refreshElapsed();
      stopElapsedTimer();
      elapsedTimer = setInterval(refreshElapsed, 1000);
    }

    function renderMetricCards(metricMap) {
      const groups = [
        {
          title: "DeepLens",
          items: [
            [["deeplens_efl_mm"], "EFL", "mm", 2],
            [["deeplens_fnum", "fnum"], "F NUM", "", 2],
            [["deeplens_fov_deg"], "FOV", "deg", 2],
            [["deeplens_distortion_pct_abs_max", "distortion_pct_abs_max"], "Distortion", "%", 2],
            [["deeplens_mtf50_edge_tan_cy_mm", "mtf50_edge_tan_cy_mm"], "MTF50 Edge T", "cy/mm", 2],
            [["deeplens_rms_spot_um_edge", "spot_rms_um_edge"], "RMS Spot Edge", "um", 2],
            [["deeplens_rms_spot_um_max"], "RMS Spot Max", "um", 2],
          ],
        },
        {
          title: "Zemax",
          items: [
            [["zemax_efl_mm"], "EFL", "mm", 2],
            [["zemax_fnum"], "F NUM", "", 2],
            [["zemax_fov_deg"], "FOV", "deg", 2],
            [["zemax_distortion_pct_abs_max"], "Distortion", "%", 2],
            [["zemax_mtf50_edge_tan_cy_mm"], "MTF50 Edge T", "cy/mm", 2],
            [["zemax_spot_rms_edge_um", "zemax_spot_rms_edge_mm"], "RMS Spot Edge", "um", 2],
            [["zemax_spot_rms_max_um", "zemax_spot_rms_max_mm"], "RMS Spot Max", "um", 2],
          ],
        },
      ];

      const pickMetric = (keys) => {
        for (const key of keys) {
          if (metricMap && metricMap[key] !== undefined && metricMap[key] !== null && metricMap[key] !== "") {
            return metricMap[key];
          }
        }
        return "-";
      };

      const html = groups
        .map((group) => {
          const itemsHtml = group.items
            .map(([keys, label, suffix, digits]) => {
              const rawValue = pickMetric(keys);
              const value = rawValue === "-" ? rawValue : formatMetricValue(rawValue, digits, suffix ? ` ${suffix}` : "");
              return `<div class="metric"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`;
            })
            .join("");
          return `
            <div class="metric-column">
              <h3 class="metric-source">${escapeHtml(group.title)}</h3>
              <div class="metric-grid">${itemsHtml}</div>
            </div>
          `;
        })
        .join("");
      metrics.innerHTML = html || `<div class="empty">No metrics yet.</div>`;
    }

    function formatMetricValue(value, digits = 2, suffix = "") {
      if (value === undefined || value === null || value === "") {
        return "-";
      }
      const numeric = Number(value);
      if (Number.isNaN(numeric)) {
        return String(value);
      }
      return `${numeric.toFixed(digits).replace(/\.?0+$/, "")}${suffix}`;
    }

    function renderFileMeta(result, preview) {
      const files = [
        ["结果目录", result.result_dir, result.result_dir_url],
        ["初始参数", preview && preview.starting_json_path, preview && preview.starting_json_url],
        ["课程学习参数", result.curriculum_json, result.curriculum_json_url],
        ["最终参数", result.final_json, result.final_json_url],
        ["Zemax ZMX", result.final_zmx, result.final_zmx_url],
        ["生成报告", result.summary_report_file, result.summary_report_file_url],
        ["指标归档", result.metrics_file, result.metrics_file_url],
        ["Zemax 分析报告", preview && preview.zemax_report_path, preview && preview.zemax_report_url],
        ["运行日志", result.log_file, result.log_file_url],
      ].filter(([, value]) => value);

      if (!files.length) {
        fileMeta.innerHTML = `<div class="empty">Result files will appear here after design execution.</div>`;
        return;
      }

      fileMeta.innerHTML = files.map(([label, value, url]) => `
        <div class="list-item">
          <h4>${escapeHtml(label)}</h4>
          <p class="file-path mono">
            ${url
              ? `<a class="file-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">[${escapeHtml(String(value).split("/").pop() || value)}](${escapeHtml(value)})</a>`
              : escapeHtml(value)}
          </p>
        </div>
      `).join("");
    }

    function renderArtifacts(result) {
      const preview = result.preview || null;
      const zemaxFigures = preview && preview.zemax_figures ? preview.zemax_figures : [];
      if (!preview || (!preview.starting_image_url && !preview.curriculum_image_url && !preview.final_image_url && !zemaxFigures.length)) {
        artifacts.innerHTML = `<div class="empty">Artifacts appear here after design execution.</div>`;
        renderFileMeta(result, preview);
        return;
      }

      const renderImagePanel = ({ title, subtitle, url, kind }) => `
        <div class="result-panel ${kind}">
          <div class="result-head">
            <div>
              <h4>${escapeHtml(title)}</h4>
              <p>${escapeHtml(subtitle)}</p>
            </div>
          </div>
          <div class="result-image-wrap">
            ${url
              ? `<img class="result-image" src="${escapeHtml(url)}" alt="${escapeHtml(title)}">`
              : `<div class="result-missing">优化中...</div>`}
          </div>
        </div>
      `;

      const zemaxSection = zemaxFigures.length
        ? `
          <div class="result-section-title">
            <h3>Zemax Analysis</h3>
            <span>${escapeHtml(preview.zemax_status || "OpticStudio results")}</span>
          </div>
          <div class="zemax-strip">
            ${zemaxFigures.map((figure, index) => renderImagePanel({
              title: figure.title || "Zemax Figure",
              subtitle: figure.subtitle || "Generated from final.zmx",
              url: figure.url,
              kind: index >= 2 || figure.key === "spot_diagram" ? "zemax zemax-wide" : "zemax",
            })).join("")}
          </div>
        `
        : (preview.zemax_error
          ? `<div class="result-missing">Zemax 分析未完成：${escapeHtml(preview.zemax_error)}</div>`
          : "");

      const params = [
        ["焦距", preview.foclen_display],
        ["F 数", preview.fnum_display],
        ["半视场", preview.rfov_display],
        ["传感器半径", preview.r_sensor_display],
        ["面数", preview.surface_count_display],
      ];

      artifacts.innerHTML = `
        <div class="result-gallery">
          <div class="result-strip">
            ${renderImagePanel({
              title: "初始",
              subtitle: "优化前的起点结构",
              url: preview.starting_image_url,
              kind: "small",
            })}
            ${renderImagePanel({
              title: "课程学习",
              subtitle: "选取课程阶段最后一张过程图",
              url: preview.curriculum_image_url,
              kind: "small",
            })}
          </div>
          ${renderImagePanel({
            title: "最终结果",
            subtitle: "微调完成后的主结果图",
            url: preview.final_image_url,
            kind: "large",
          })}
          ${zemaxSection}
          <div class="result-params">
            ${params.map(([label, value]) => `
              <div class="param-chip">
                <span>${escapeHtml(label)}</span>
                <strong>${escapeHtml(value || "-")}</strong>
              </div>
            `).join("")}
          </div>
        </div>
      `;
      renderFileMeta(result, preview);
    }

    function renderReferences(rows) {
      if (!rows || !rows.length) {
        references.innerHTML = `<div class="empty">Case references will appear here.</div>`;
        return;
      }

      references.innerHTML = rows.map((row) => `
        <div class="list-item">
          <h4>${escapeHtml(row.title || "Untitled")}</h4>
          <p>${escapeHtml(row.snippet || "No summary.")}</p>
        </div>
      `).join("");
    }

    function appendTimeline(message) {
      const text = normalizeTraceMessage(message);
      if (timeline.children.length === 1 && timeline.children[0].textContent.includes("LensBot 已就绪")) {
        timeline.innerHTML = "";
      }
      const li = document.createElement("li");
      li.textContent = text;
      timeline.appendChild(li);
      timeline.scrollTop = timeline.scrollHeight;
    }

    function normalizeTraceMessage(message) {
      const raw = String(message || "").trim();
      if (!raw) {
        return "正在整理设计思路。";
      }

      const normalized = raw
        .replace(/\s+/g, " ")
        .replace(/[。！？!?；;]+$/g, "")
        .trim();
      const cleaned = normalized
        .replace(/^LensBot\s+/, "")
        .replace(/^已接受任务，准备启动智能体$/i, "任务：已接受，准备启动智能体。")
        .replace(/^流程已完成$/i, "报告归档：流程已完成。")
        .replace(/^Memory recording skipped:.*$/i, "记忆归档遇到提示，已跳过写入。")
        .replace(/^Lens design failed:.*$/i, "镜头设计失败。")
        .replace(/^(需求解析|初始结构选择|优化与评估|报告归档)(开始|完成)$/i, "$1：$2。")
        .replace(/^正在处理：将用户意图解析为光学设计上下文$/i, "需求解析：准备上下文。")
        .replace(/^正在处理：选择并验证初始光学结构$/i, "初始结构选择：准备参考检索。")
        .replace(/^正在处理：优化、评估并判断光学性能$/i, "优化与评估：准备运行优化。")
        .replace(/^正在处理：归档运行结果并更新分层记忆$/i, "报告归档：准备归档结果。")
        .replace(/^Reading ZEMAX Index\.?$/i, "正在读取 ZEMAX 索引。")
        .replace(/^Read ZEMAX Index with (\d+) entries\.?$/i, "已读取 ZEMAX 索引，共 $1 个案例。")
        .replace(/^Selected reference case ([^:：]+):\s*(.+)$/i, "已选择参考案例 $1：$2。")
        .replace(/^Generating DeepLens starting structure\.?$/i, "正在生成 DeepLens 初始结构。")
        .replace(/^正在读取 ZEMAX 索引。?$/i, "初始结构选择：读取 ZEMAX 索引。")
        .replace(/^已读取 ZEMAX 索引，共 (\d+) 个案例。?$/i, "初始结构选择：已读取 $1 个案例。")
        .replace(/^已选择参考案例 ([^:：]+)：(.+)。?$/i, "初始结构选择：选择参考案例 $1。")
        .replace(/^正在生成 DeepLens 初始结构。?$/i, "初始结构选择：生成 DeepLens 初始结构。")
        .replace(/^检索参考案例：根据记忆和目标检索本地光学参考作为初始结构$/i, "初始结构选择：生成参考初始结构。")
        .replace(/^Action:\s*初始化镜头自动设计任务$/i, "优化与评估：初始化镜头自动设计任务。")
        .replace(/^Action:\s*执行课程学习和微调$/i, "优化与评估：执行课程学习和微调。")
        .replace(/^Observation:\s*设计完成，详细过程已写入日志文件$/i, "优化与评估：设计完成，日志已归档。")
        .replace(/^Action:\s*启动 Zemax OpticStudio 并载入 final\.zmx$/i, "Zemax 分析：载入 final.zmx。")
        .replace(/^Action:\s*执行 Zemax FFT MTF 与 Spot 分析$/i, "Zemax 分析：执行 FFT MTF 与 Spot 分析。")
        .replace(/^Action:\s*追迹光线并生成 Zemax Spot Diagram$/i, "Zemax 分析：生成 Spot Diagram。")
        .replace(/^Action:\s*绘制 Zemax 分析图$/i, "Zemax 分析：绘制分析图。")
        .replace(/^Observation:\s*Zemax 分析完成，结果和图像已归档$/i, "Zemax 分析：结果和图像已归档。")
        .replace(/^Lens optimization finished\.?$/i, "镜头优化已完成。")
        .replace(/^Lens metric evaluation finished\.?$/i, "镜头像质评估已完成。")
        .replace(/^Zemax analysis finished\.?$/i, "Zemax 分析已完成。")
        .replace(/^Reference seeding completed\.?$/i, "参考结构生成已完成。")
        .replace(/^Design accepted by evaluator\.?$/i, "评估器已接受当前设计。")
        .replace(/^Design completed with evaluator issues\.?$/i, "设计已完成，但评估器发现问题。")
        .replace(/^evaluateacceptance：/i, "验收设计结果：")
        .replace(/^运行镜头优化：当前还没有优化结果，先运行配置好的算法引擎$/i, "优化与评估：运行镜头优化。")
        .replace(/^评估优化结果：优化器已生成结果，先评估像质指标再判断可信度$/i, "优化与评估：评估优化结果。")
        .replace(/^分析 Zemax 结果：用 Zemax 独立评估导出的 final\.zmx$/i, "Zemax 分析：完成独立评估。")
        .replace(/^归档报告和记忆：归档指标与报告，并更新可复用的光学设计记忆$/i, "报告归档：归档报告和记忆。")
        .replace(/^检查：确认优化预算已明确，再继续后续流程$/i, "需求解析：确认优化预算。")
        .replace(/^检查：检查选中的初始结构是否适合进入优化$/i, "初始结构选择：检查初始结构。")
        .replace(/^Action:\s*/i, "")
        .replace(/^Observation:\s*/i, "")
        .replace(/^([A-Za-z]+Agent)\s+开始处理：/, "正在处理：")
        .replace(/^开始处理：/, "正在处理：");

      const sentences = cleaned
        .split(/[。！？!?；;]+/)
        .map((item) => item.trim())
        .filter(Boolean)
        .slice(0, 1);

      if (!sentences.length) {
        return "正在整理设计思路。";
      }

      return `${sentences.join("。")}。`;
    }

    function resetView() {
      if (currentSource) {
        currentSource.close();
        currentSource = null;
      }
      stopElapsedTimer();
      runStartTime = null;
      elapsedPill.textContent = "00:00";
      timeline.innerHTML = "<li>LensBot 已就绪。</li>";
      metrics.innerHTML = `<div class="empty">Run the agent to populate IQA metrics.</div>`;
      artifacts.innerHTML = `<div class="empty">Artifacts appear here after design execution.</div>`;
      references.innerHTML = `<div class="empty">Case references will appear here.</div>`;
      fileMeta.innerHTML = `<div class="empty">Result files will appear here after design execution.</div>`;
      runBtn.disabled = false;
      setStatus("空闲", "等待新的设计任务。");
    }

    function fillDefaults() {
      document.getElementById("nl_prompt").value = "我需要一个 52mm 焦距、F/2.9、43 度视场的镜头。";
      document.getElementById("foclen").value = defaults.params.foclen;
      document.getElementById("fov").value = defaults.params.fov;
      document.getElementById("fnum").value = defaults.params.fnum;
      document.getElementById("bfl").value = defaults.params.bfl;
      document.getElementById("thickness").value = defaults.params.thickness;
      document.getElementById("iterations").value = defaults.params.curriculum.iterations;
      document.getElementById("spp").value = defaults.params.curriculum.spp;
      document.getElementById("test_per_iter").value = defaults.params.curriculum.test_per_iter;
      document.getElementById("fine_tune_iterations").value = defaults.params.fine_tune.iterations;
      document.getElementById("fine_tune_spp").value = defaults.params.fine_tune.spp;
      document.getElementById("fine_tune_test_per_iter").value = defaults.params.fine_tune.test_per_iter;
    }

    async function startRun() {
      if (currentSource) {
        currentSource.close();
        currentSource = null;
      }

      runBtn.disabled = true;
      startElapsedTimer();
      timeline.innerHTML = "";
      metrics.innerHTML = `<div class="empty">等待执行...</div>`;
      artifacts.innerHTML = `<div class="empty">等待执行...</div>`;
      references.innerHTML = `<div class="empty">等待执行...</div>`;
      fileMeta.innerHTML = `<div class="empty">等待执行...</div>`;

      const payload = {
        mode: currentMode,
        nl_prompt: document.getElementById("nl_prompt").value,
        foclen: Number(document.getElementById("foclen").value),
        fov: Number(document.getElementById("fov").value),
        fnum: Number(document.getElementById("fnum").value),
        bfl: Number(document.getElementById("bfl").value),
        thickness: Number(document.getElementById("thickness").value),
        iterations: Number(document.getElementById("iterations").value),
        spp: Number(document.getElementById("spp").value),
        test_per_iter: Number(document.getElementById("test_per_iter").value),
        fine_tune_iterations: Number(document.getElementById("fine_tune_iterations").value),
        fine_tune_spp: Number(document.getElementById("fine_tune_spp").value),
        fine_tune_test_per_iter: Number(document.getElementById("fine_tune_test_per_iter").value),
      };

      setStatus("运行中", "正在创建任务并打开实时流。");

      const rsp = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await rsp.json();
      if (!rsp.ok) {
        stopElapsedTimer();
        runStartTime = null;
        elapsedPill.textContent = "00:00";
        runBtn.disabled = false;
        setStatus("失败", data.error || "创建任务失败。");
        return;
      }

      currentSource = new EventSource(`/api/stream?run_id=${encodeURIComponent(data.run_id)}`);

      currentSource.addEventListener("progress", (event) => {
        const payload = JSON.parse(event.data);
        appendTimeline(payload.message);
        setStatus("运行中", payload.message);
      });

      currentSource.addEventListener("artifact", (event) => {
        const payload = JSON.parse(event.data);
        renderArtifacts(payload);
      });

      currentSource.addEventListener("result", (event) => {
        const payload = JSON.parse(event.data);
        stopElapsedTimer();
        refreshElapsed();
        renderMetricCards(payload.metrics || {});
        renderArtifacts(payload);
        renderReferences(payload.references || []);
        setStatus(
          payload.ok ? "完成" : "失败",
          payload.ok
            ? "设计已完成，结果图、关键指标和文件索引已更新。"
            : (payload.summary || "运行已结束。")
        );
      });

      currentSource.addEventListener("run_error", (event) => {
        const payload = JSON.parse(event.data);
        stopElapsedTimer();
        refreshElapsed();
        appendTimeline(payload.message || "运行失败。");
        setStatus("失败", payload.message || "运行失败。");
      });

      currentSource.addEventListener("done", () => {
        runBtn.disabled = false;
        if (currentSource) {
          currentSource.close();
          currentSource = null;
        }
      });

      currentSource.onerror = () => {
        stopElapsedTimer();
        refreshElapsed();
        runBtn.disabled = false;
      };
    }

    modeButtons.forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
    runBtn.addEventListener("click", startRun);
    resetBtn.addEventListener("click", resetView);

    fillDefaults();
    setMode("自然语言输入");
    resetView();
    renderMetricCards({});
  </script>
</body>
</html>
"""


@dataclass
class RunState:
    run_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    condition: threading.Condition = field(default_factory=threading.Condition)

    def publish(self, event: dict[str, Any]) -> None:
        with self.condition:
            self.events.append(event)
            self.condition.notify_all()

    def close(self) -> None:
        with self.condition:
            self.done = True
            self.condition.notify_all()


RUNS: dict[str, RunState] = {}
RUNS_LOCK = threading.Lock()


def build_agent() -> LensResearchAgent:
    return LensResearchAgent(load_default_params(PROJECT_ROOT), PROJECT_ROOT)


def build_defaults_payload() -> dict[str, Any]:
    params = load_default_params(PROJECT_ROOT)
    return {"params": asdict(params)}


def build_index_html() -> str:
    return HTML.replace("__DEFAULTS__", json.dumps(build_defaults_payload(), ensure_ascii=False))


def _result_file_url(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    try:
        relative_path = path.resolve().relative_to((PROJECT_ROOT / "results").resolve())
    except ValueError:
        return None
    return "/results/" + "/".join(relative_path.parts)


def _format_preview_value(value: Any, suffix: str = "", digits: int = 2) -> str:
    if value in (None, ""):
        return "-"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{numeric:.{digits}f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def _display_workspace_path(path: str | None) -> str | None:
    if not path:
        return None
    try:
        workspace_root = PROJECT_ROOT.parents[2].resolve()
        relative_path = Path(path).resolve().relative_to(workspace_root)
        return relative_path.as_posix()
    except (ValueError, OSError):
        return path


def _load_json_dict(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _pick_curriculum_image(result_dir: Path) -> Path | None:
    candidates = sorted(
        result_dir.glob("curriculum/iter*.png"),
        key=lambda item: int("".join(ch for ch in item.stem if ch.isdigit()) or "0"),
    )
    return candidates[-1] if candidates else None


def _pick_starting_file(result_dir: Path, suffix: str) -> Path | None:
    normalized = result_dir / f"starting-point{suffix}"
    if normalized.exists():
        return normalized
    candidates = sorted(result_dir.glob(f"starting-point_*{suffix}"))
    return candidates[-1] if candidates else None


def _build_zemax_figure_payload(root: Path, metrics: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    zemax = metrics.get("zemax") if isinstance(metrics.get("zemax"), dict) else {}
    title_map = {
        "fft_mtf": ("FFT MTF", "Tangential and sagittal MTF from OpticStudio"),
        "spot_summary": ("Spot Radius", "RMS and geometric spot radius by field"),
        "spot_diagram": ("Spot Diagram", "Ray trace point cloud relative to centroid"),
        "zemax_summary": ("Zemax Summary", "Fallback summary when spot diagram tracing is unavailable"),
    }

    figures = []
    for item in zemax.get("figures", []):
        path_value = item.get("path")
        if not path_value:
            continue
        path = Path(str(path_value))
        if not path.exists():
            continue
        title, subtitle = title_map.get(str(item.get("key")), (item.get("title", "Zemax Figure"), "Generated from final.zmx"))
        figures.append(
            {
                "key": item.get("key"),
                "title": title,
                "subtitle": subtitle,
                "path": _display_workspace_path(str(path)),
                "url": _result_file_url(path),
            }
        )

    if not figures:
        scanned_paths = [
            *sorted((root / "zemax-analysis").glob("*.png")),
            *sorted((root / "zmx_metrics_figures").glob("*.png")),
        ]
        order = {"fft_mtf": 0, "spot_summary": 1, "spot_diagram": 2, "zemax_summary": 3}
        scanned_paths.sort(key=lambda path: (order.get(path.stem, 99), path.name))
        seen_keys: set[str] = set()
        for path in scanned_paths:
            key = path.stem
            if key in seen_keys:
                continue
            seen_keys.add(key)
            title, subtitle = title_map.get(key, (path.stem.replace("_", " ").title(), "Generated from final.zmx"))
            figures.append(
                {
                    "key": key,
                    "title": title,
                    "subtitle": subtitle,
                    "path": _display_workspace_path(str(path)),
                    "url": _result_file_url(path),
                }
            )

    report_file = Path(str(zemax.get("report_file", root / "zemax-analysis" / "zemax_report.json"))) if isinstance(zemax, dict) else root / "zemax-analysis" / "zemax_report.json"
    meta = {
        "zemax_status": "OpticStudio analysis complete" if zemax.get("ok") else "OpticStudio analysis pending",
        "zemax_error": zemax.get("error") or zemax.get("spot_diagram_error"),
        "zemax_report_path": _display_workspace_path(str(report_file)) if report_file.exists() else None,
        "zemax_report_url": _result_file_url(report_file) if report_file.exists() else None,
    }
    return figures, meta


def _build_preview_payload(result_dir: str | None, metrics: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not result_dir:
        return None

    root = Path(result_dir)
    if not root.exists():
        return None

    starting_json = _pick_starting_file(root, ".json")
    starting_image = _pick_starting_file(root, ".png")
    final_json = root / "final.json"
    starting_data = _load_json_dict(starting_json)
    final_data = _load_json_dict(final_json)
    metric_map = metrics or {}
    zemax_figures, zemax_meta = _build_zemax_figure_payload(root, metric_map)

    surfaces = final_data.get("surfaces") or starting_data.get("surfaces") or []
    payload = {
        "starting_image_url": _result_file_url(starting_image),
        "curriculum_image_url": _result_file_url(_pick_curriculum_image(root)),
        "final_image_url": _result_file_url(root / "final.png"),
        "starting_json_path": _display_workspace_path(str(starting_json)) if starting_json and starting_json.exists() else None,
        "starting_json_url": _result_file_url(starting_json),
        "foclen_display": _format_preview_value(final_data.get("foclen") or starting_data.get("foclen"), " mm"),
        "fnum_display": _format_preview_value(
            metric_map.get("fnum") or final_data.get("fnum") or starting_data.get("fnum")
        ),
        "rfov_display": _format_preview_value(metric_map.get("rfov"), " deg"),
        "r_sensor_display": _format_preview_value(
            metric_map.get("r_sensor") or final_data.get("r_sensor") or starting_data.get("r_sensor"),
            " mm",
        ),
        "surface_count_display": str(len(surfaces)) if surfaces else "-",
        "zemax_figures": zemax_figures[:3],
    }
    payload.update(zemax_meta)
    return payload


def _json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _start_run(payload: dict[str, Any]) -> str:
    run_id = uuid.uuid4().hex[:10]
    state = RunState(run_id=run_id)
    with RUNS_LOCK:
        RUNS[run_id] = state
    defaults = load_default_params(PROJECT_ROOT)

    def worker() -> None:
        agent = build_agent()
        run_payload = dict(payload)
        run_payload["curriculum"] = {
            "iterations": run_payload.get("iterations", defaults.curriculum.iterations),
            "spp": run_payload.get("spp", defaults.curriculum.spp),
            "test_per_iter": run_payload.get("test_per_iter", defaults.curriculum.test_per_iter),
        }
        run_payload["fine_tune"] = {
            "iterations": run_payload.get("fine_tune_iterations", defaults.fine_tune.iterations),
            "spp": run_payload.get("fine_tune_spp", defaults.fine_tune.spp),
            "test_per_iter": run_payload.get("fine_tune_test_per_iter", defaults.fine_tune.test_per_iter),
        }
        agent_input = build_agent_input(PROJECT_ROOT, payload=run_payload)

        state.publish({"event": "progress", "message": "LensBot 已接受任务，准备启动智能体。"})

        try:
            def publish_artifact(result_dir: str) -> None:
                state.publish(
                    {
                        "event": "artifact",
                        "result_dir": _display_workspace_path(result_dir),
                        "result_dir_url": _result_file_url(Path(result_dir)),
                        "preview": _build_preview_payload(result_dir),
                    }
                )

            result = agent.run(
                agent_input,
                progress_cb=lambda message: state.publish({"event": "progress", "message": message}),
                artifact_cb=publish_artifact,
            )
            state.publish(
                {
                    "event": "result",
                    "ok": result.ok,
                    "summary": result.summary,
                    "result_dir": _display_workspace_path(result.result_dir),
                    "result_dir_url": _result_file_url(Path(result.result_dir)) if result.result_dir else None,
                    "curriculum_json": _display_workspace_path(result.curriculum_json),
                    "curriculum_json_url": _result_file_url(Path(result.curriculum_json)) if result.curriculum_json else None,
                    "final_json": _display_workspace_path(result.final_json),
                    "final_json_url": _result_file_url(Path(result.final_json)) if result.final_json else None,
                    "final_zmx": _display_workspace_path(result.final_zmx),
                    "final_zmx_url": _result_file_url(Path(result.final_zmx)) if result.final_zmx else None,
                    "summary_report_file": _display_workspace_path(result.summary_report_file),
                    "summary_report_file_url": _result_file_url(Path(result.summary_report_file)) if result.summary_report_file else None,
                    "metrics_file": _display_workspace_path(result.metrics_file),
                    "metrics_file_url": _result_file_url(Path(result.metrics_file)) if result.metrics_file else None,
                    "log_file": _display_workspace_path(result.log_file),
                    "log_file_url": _result_file_url(Path(result.log_file)) if result.log_file else None,
                    "metrics": result.metrics,
                    "preview": _build_preview_payload(result.result_dir, result.metrics),
                    "references": result.references,
                    "timeline": result.timeline,
                }
            )
        except Exception as exc:  # pragma: no cover - UI boundary
            state.publish({"event": "run_error", "message": f"Lens design failed: {exc}"})
        finally:
            state.publish({"event": "done"})
            state.close()

    threading.Thread(target=worker, daemon=True).start()
    return run_id


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "LensBotDashboard/1.0"

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = build_index_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            return
        if parsed.path == "/api/defaults":
            body = json.dumps(build_defaults_payload(), ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return
        if parsed.path.startswith("/results/"):
            file_path = self._resolve_result_path(parsed.path)
            if file_path is None or not file_path.is_file():
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            return
        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = build_index_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if parsed.path == "/api/defaults":
            _json_response(self, build_defaults_payload())
            return

        if parsed.path == "/api/stream":
            query = parse_qs(parsed.query)
            run_id = query.get("run_id", [""])[0]
            with RUNS_LOCK:
                state = RUNS.get(run_id)
            if state is None:
                _json_response(self, {"error": "Run not found."}, status=404)
                return
            self._stream_run(state)
            return

        if parsed.path.startswith("/results/"):
            file_path = self._resolve_result_path(parsed.path)
            if file_path is None or not file_path.is_file():
                _json_response(self, {"error": "Not found."}, status=404)
                return
            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            with file_path.open("rb") as handle:
                self.wfile.write(handle.read())
            return

        _json_response(self, {"error": "Not found."}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/run":
            _json_response(self, {"error": "Not found."}, status=404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            _json_response(self, {"error": "Invalid JSON body."}, status=400)
            return

        required = ["mode"]
        missing = [key for key in required if key not in payload]
        if missing:
            _json_response(self, {"error": f"Missing fields: {', '.join(missing)}"}, status=400)
            return

        run_id = _start_run(payload)
        _json_response(self, {"run_id": run_id}, status=202)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _stream_run(self, state: RunState) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        index = 0
        while True:
            with state.condition:
                while index >= len(state.events) and not state.done:
                    state.condition.wait(timeout=1.0)
                    try:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return

                pending = state.events[index:]
                is_done = state.done and index >= len(state.events)

            for event in pending:
                chunk = (
                    f"event: {event['event']}\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                ).encode("utf-8")
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
            index += len(pending)

            if is_done or (state.done and index >= len(state.events)):
                return

    @staticmethod
    def _resolve_result_path(request_path: str) -> Path | None:
        relative = request_path.removeprefix("/results/").strip("/")
        if not relative:
            return None
        base = (PROJECT_ROOT / "results").resolve()
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate


def run_server(host: str = HOST, port: int = PORT) -> None:
    configured_port = int(os.getenv("LENSBOT_PORT", str(port)))
    server = None
    bound_port = configured_port

    for candidate in range(configured_port, configured_port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate), DashboardHandler)
            bound_port = candidate
            break
        except OSError:
            continue

    if server is None:
        raise OSError(
            f"Unable to bind LensBot dashboard on {host}. "
            f"Tried ports {configured_port}-{configured_port + 19}."
        )

    print(f"LensBot dashboard running at http://{host}:{bound_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
