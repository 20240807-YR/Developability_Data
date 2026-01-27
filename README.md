# Developability_Data

## Project Overview

본 프로젝트는 항체 Developability 문제를 “더 정확한 예측 모델을 구축하는 문제”가 아니라, 예측이 가능한 환경에서도 설계 의사결정이 왜 구조적으로 불안정해지는가를 규명하는 의사결정 거버넌스 문제로 재정의합니다. 항체 설계 과정에서는 예측 결과가 존재함에도 불구하고 예측 변동을 근거로 한 설계 개입과 유지의 반복적 토글, 규칙을 강화할수록 누적되는 설계 불안정성, 물성이 회복되는 국면에서도 발생하는 불필요한 추가 개입, 그리고 설계 실패 이후 시스템 자체가 더 이상 운영되지 못하는 구조적 붕괴 현상이 반복적으로 관찰됩니다. 본 프로젝트의 목표는 설계를 계속 “잘” 수행하는 것이 아니라, 위험 상태에 진입했을 때 설계를 구조적으로 중단할 수 있으며, 설계 중단 이후에도 시스템이 차선 운영 모드로 전환되어 지속적으로 운영 가능함을 증명하는 것입니다.

⸻

## Core Structure Overview (Core 1–11)

본 프로젝트는 총 11개의 Core로 구성되며, 전체 구조는 두 단계로 구분됩니다. Core 1–5에서는 예측 성능이나 규칙 정교화가 항체 설계 실패의 병목이 아님을 구조적으로 고정하는 단계이며, Core 6–11에서는 상태 기반 거버넌스를 도입하여 설계 개입 제한, fallback 전환, 그리고 설계 종료 이후의 운영 모드까지 포함하는 의사결정 시스템을 완성합니다.

⸻

### Core 1 — Controlled Predictability Setup

Prediction Is Available, Yet Decision Failure Still Emerges

본 Core의 목적은 항체 Developability 설계 실패가 “예측이 불가능하기 때문에 발생하는 문제”가 아님을 의도적으로 먼저 고정하는 데 있습니다. 본 프로젝트는 처음부터 예측 성능 향상을 연구 목표로 설정하지 않으며, 예측이 일정 수준 가능함에도 불구하고 설계 의사결정이 왜 불안정해지는지를 분석하기 위한 통제된 출발점을 마련합니다. 분석 결과 항체 Developability는 완전한 블랙박스가 아니며 국소적 상태에서는 예측 가능함이 확인되었음에도 불구하고 설계 실패가 반복적으로 발생하였고, 이를 통해 실패의 원인이 예측 이후 단계에 존재함을 고정합니다.

⸻

### Core 2 — Prediction-centered Design Attempt

When Prediction Becomes the Primary Design Trigger

본 Core에서는 Core 1에서 확보한 예측 가능성을 전제로, 예측 악화 시 설계 개입을 수행하고 예측 개선 시 설계를 유지하는 단순한 예측 중심 의사결정 규칙을 적용합니다. 일부 설계 단계에서는 단기적인 물성 개선이 관찰되었으나, 전체 설계 과정 차원에서는 개입과 유지의 잦은 토글, 불필요한 mutation 누적, 그리고 장기적인 설계 불안정성 증가가 반복적으로 발생하였습니다. 이를 통해 예측 값만으로는 설계 판단에 필요한 맥락 정보를 충분히 제공하지 못함을 확인합니다.

⸻

### Core 3 — Rule Intensification Failure

Why More Rules Did Not Resolve Decision Instability

본 Core에서는 Core 2에서 관찰된 설계 불안정성이 규칙의 단순성 때문이라는 가설 하에, 다중 조건 규칙, 히스테리시스 조건, 변경 폭 제한, 지속 시간 조건 등 규칙을 점진적으로 확장하는 실험을 수행합니다. 그 결과 규칙이 증가할수록 규칙 간 충돌과 예외 조건이 폭증하였고, 설계 결과의 해석 가능성이 오히려 저하되는 현상이 관찰되었습니다. 이를 통해 설계 불안정성의 원인이 규칙의 부족이 아니라 설계 입력으로 사용되는 정보 구조 자체의 불안정성에 있음을 확인합니다.

⸻

Core 4 — Structural Contrast

Battery Degradation vs Antibody Design

본 Core에서는 항체 설계 구조를 배터리 관리 시스템과 구조적으로 대비합니다. 배터리 시스템은 SOH, 열화율 등 상태 변수를 지속적으로 계측하며 결과보다 과정을 중심으로 제어가 이루어지는 반면, 항체 설계는 결과 물성 중심의 판단 구조를 가지며 상태 계측이 부재합니다. 이를 통해 시스템 안정성은 예측 정확도보다 상태 관측 밀도에 의해 구조적으로 결정된다는 핵심 통찰을 도출합니다.

⸻

### Core 5 — Structural Implication

Core 1–4의 분석을 종합한 결과, 항체 Developability 설계의 병목은 예측 성능이나 규칙 정교화가 아니라 설계 과정에서 상태를 직접 계측하지 못하는 구조적 한계에 있음을 결론으로 고정합니다.

⸻

### Core 6 — State Observability → Governance Variable

본 Core에서는 SoD(State of Developability)와 SoMS(State of Metric/Model Stress)를 모델 feature나 예측 보조 지표가 아닌, 설계를 계속 수행해도 되는지를 판단하기 위한 governance state로 재정의합니다. 이를 통해 설계 과정에 연속적인 상태 축이 삽입되며, 상태 누적이 실제로 설계 개입 권한을 제한할 수 있음을 로그 기반으로 고정합니다.

⸻

### Core 7 — Controlled Governance Test

본 Core에서는 상태 기반 거버넌스가 실제로 설계 개입을 제한할 수 있는지를 검증합니다. 상태는 계산하지만 개입을 항상 허용하는 Case A와, 상태 기반 veto/freeze가 존재하는 Case B를 비교하며, 성능 지표가 아닌 개입 차단 여부, 금지 실패 영역 진입 방지 여부, 설계 행동 자유도 제한 여부를 평가 기준으로 사용합니다. 성공은 “이제 설계를 할 수 없게 되었다”는 사실을 데이터로 증명하는 것으로 정의됩니다.

⸻

### Core 8 — Designing a System That Can Refuse to Design

본 Core에서는 설계를 “안 하는 선택”이 아니라, 구조적으로 설계를 할 수 없도록 만드는 시스템을 설계합니다. 성능 정체, 탐색 종료, 설계 공간 봉쇄는 허용되며, 폭주, 진동, 무제한 누적 스트레스는 구조적으로 금지됩니다.

⸻

### Fallback Redefinition (Project Core Concept)

본 프로젝트에서 fallback은 실패 회피 수단이 아니라, 누적 기반으로만 발동되고 단계적으로 권한이 박탈되며 즉시 반응하지 않는 사전에 설계된 차선 운영 모드로 정의됩니다.

⸻

### Core 9 — State Trajectory Forecasting for Governance

본 Core에서의 예측은 성능 목적이 아니라 SoMS 폭주 가능성, oscillation 비회복 진입, conflict density 자기증폭을 사전에 감지하여 fallback을 예약하기 위한 신호로만 사용됩니다.

⸻

### Core 10 — State-aware Antibody Allocation After Design Shutdown

본 Core에서는 Design과 Operation을 명확히 분리하며, 설계 시스템은 종료되지만 운영 시스템은 계속 작동함을 전제로 합니다. 추가 mutation 없이 유지 가능하고 SoMS trajectory 악화가 없으며 미래 설계 가능성을 보존하는 항체를 선택함으로써, 설계 종료 이후에도 시스템이 운영 가능함을 증명합니다.

⸻

### Core 11 — Reproducible Governance System

본 Core의 목적은 정책 기반 운영이 실제로 작동함을 보이고, fallback이 예외가 아닌 모드 전환임을 증명하며, 동일 입력에 대해 동일 결과가 재현되고 사람이 이해 가능한 설명이 제공되는 시스템을 완성하는 데 있습니다.

⸻

### Final Statement

본 프로젝트는 항체 Developability를 성능 최적화 문제가 아닌, 설계 개입을 언제, 왜, 어떻게 중단해야 하는지를 구조적으로 정의하는 의사결정 거버넌스 문제로 재정의합니다. 설계 실패 이후에도 미래 설계 가능성을 보존하며 시스템을 운영하는 것이 본 프로젝트의 최종 목표입니다.