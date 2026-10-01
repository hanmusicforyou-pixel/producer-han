# CLAUDE.md — Producer HAN Portfolio

Figma 디자인을 이 코드베이스에 통합할 때 따를 규칙. **코드를 쓰기 전에 반드시 읽을 것.**

---

## 0. 가장 중요한 경고 — Figma MCP 기본 출력을 그대로 쓰면 안 된다

`get_design_context` 는 보통 **React 컴포넌트 + Tailwind 클래스**를 돌려준다. 이 레포는 그 중 **어느 것도 쓰지 않는다.**

| Figma MCP 기본 출력 | 이 레포의 실제 | 조치 |
|---|---|---|
| React / JSX | **바닐라 HTML** | JSX → HTML 수동 변환 |
| Tailwind 유틸리티 클래스 | **직접 작성한 플랫 CSS 클래스** | 전부 버리고 `.card` 계열 패턴으로 재작성 |
| `import` / 모듈 | **빌드 시스템 없음** | import 전부 제거 |
| 별도 `.tsx` / `.css` 파일 | **`index.html` 단일 파일** | 새 파일 만들지 말 것 |
| 하드코딩 hex (`#060608`) | **CSS 변수 (`var(--bg-base)`)** | 아래 §1 매핑표로 치환 |
| `download_assets` 로 PNG/SVG 추출 | **래스터 애셋 0개 — CSS로만 그린다** | §4 먼저 읽을 것 |

> **변환 원칙:** Figma에서 가져오는 것은 *코드*가 아니라 **레이아웃 값과 디자인 의도**다. 코드는 이 파일의 기존 패턴으로 다시 쓴다.

---

## 1. 디자인 토큰

### 어디에 있나
`index.html:12-26` — 단일 `:root` 블록. **토큰 파일도, 변환 파이프라인(Style Dictionary 등)도 없다.**

```css
:root {
    --bg-base: #060608;
    --glass-bg: rgba(18,18,22,0.55);
    --glass-border: rgba(255,255,255,0.07);
    --glass-border-hover: rgba(255,255,255,0.18);
    --text-primary: #f0f0f5;
    --text-muted: #7a7a8a;
    --text-dim: #3a3a4a;
    --accent: #c8c8dc;
    --gold: #c9a84c;
    --blur-strength: blur(24px);
    --radius-lg: 22px;
    --radius-md: 14px;
    --transition: 0.4s cubic-bezier(0.165,0.84,0.44,1);
}
```

**토큰은 13개뿐이다.** Figma에서 새 색이 나오면 먼저 **기존 13개 중 하나로 매핑되는지** 확인하라. 안 되면 `:root` 에 추가하고, 인라인 hex 로 박지 말 것.

### Figma 변수 → CSS 변수 매핑

| Figma에서 보일 값 | 매핑할 변수 | 용도 |
|---|---|---|
| `#060608`, 가장 어두운 배경 | `--bg-base` | `body`, 페이지 바탕 |
| 반투명 패널 채움 | `--glass-bg` | 카드·패널 배경 |
| 1px 미세 보더 | `--glass-border` | 기본 보더 |
| hover 시 밝아지는 보더 | `--glass-border-hover` | hover/active 보더 |
| `#f0f0f5`, 본문 흰색 | `--text-primary` | 제목·본문 |
| `#7a7a8a`, 회색 본문 | `--text-muted` | 설명문·보조 텍스트 |
| `#3a3a4a`, 가장 흐린 회색 | `--text-dim` | eyebrow·라벨·placeholder |
| `#c8c8dc`, 연보라 | `--accent` | 링크, 모달 아이콘 |
| `#c9a84c`, 금색 | `--gold` | **별점 선택 상태 전용** |
| `blur(24px)` | `--blur-strength` | 모든 `backdrop-filter` |
| `22px` 라운드 | `--radius-lg` | 카드·패널 |
| `14px` 라운드 | `--radius-md` | 입력·버튼·상태 배너 |
| 0.4s 이징 | `--transition` | 모든 hover 트랜지션 |

### 토큰화 안 된 값들 (드리프트 주의)

Figma 디자인이 이 값들을 건드리면 **토큰으로 승격시킬지 먼저 판단**하라:

- `#050508` (`index.html:59`), `#d0d0e8` (`:60`), `#d0d0e5` (`:131`) — 버튼 전경·hover
- `#060608` (`:130`) — `--bg-base` 와 같은 값인데 하드코딩됨. **고쳐도 좋다**
- `#ffffff` → `#9090b0` (`:55`) — **Hero 제목 텍스트 그라디언트.** `background-clip:text` 로 구현. Figma에서 Hero를 만지면 가장 먼저 마주칠 값이다
- `#2a2a35` (`:33`) — 스크롤바 thumb
- `#0c0c12` (`:154`) — 모달 배경
- `26px` (`:154`) 모달 라운드, `50px` (`:58`) pill 버튼 — 라운드 토큰 체계 밖
- 상태 색 (`:142-143`) — success/error 하드코딩
- 섹션 패딩 `130px 6%` (`:67`) — 간격 토큰 없음

> 간격(spacing) 토큰은 **아예 없다.** Figma의 8pt 그리드를 그대로 CSS 변수로 쏟아붓지 말고, 기존 리터럴 값 체계를 따르라.

---

## 2. 컴포넌트 라이브러리

**없다.** Storybook 도, 컴포넌트 디렉터리도, 프레임워크도 없다. `index.html` 의 `<style>` 블록 안에 **플랫 CSS 클래스**가 섹션별 주석으로 묶여 있다.

```
/* NAV */      :35    /* SECTIONS */  :66    /* FORMS */     :107
/* HERO */     :43    /* CARDS */     :72    /* DOWNLOAD */  :145
/* MODAL */    :151   /* FOOTER */    :161   /* RESPONSIVE */ :166
```

### 네이밍 규약
BEM 이 아니다. **`블록-요소` 단일 하이픈 플랫 구조**:

```
.card  .card-visual  .card-body  .card-meta  .card-title  .card-desc
.form-panel  .form-row  .form-group  .form-label  .form-control
.hero  .hero-content  .hero-label  .hero-sub  .hero-cta  .hero-scroll
.modal  .modal-box  .modal-icon  .modal-sub
```

변형(variant)은 **별도 클래스를 덧붙인다**:
```html
<button class="btn btn-outline">          <!-- :130, :133 -->
<a class="btn-hero btn-hero-primary">     <!-- :58, :59 -->
<a class="btn-hero btn-hero-ghost">       <!-- :58, :61 -->
```

→ **Figma 컴포넌트 variant 는 이 패턴으로 옮긴다.** `.btn--outline` 이나 `.btn.is-outline` 로 쓰지 말 것.

### 카드 추가하기 (가장 흔한 작업)

프로젝트 카드 구조는 `index.html:214-224` 가 기준이다:

```html
<div class="card delay-1">
    <div class="card-visual visual-luna">   <!-- 작품별 전용 비주얼 클래스 -->
        <div class="v-moon"></div>
        <span class="v-label">LUNA</span>
    </div>
    <div class="card-body">
        <span class="card-meta">Art Planning / Script</span>
        <h3 class="card-title">달의 여신 루나</h3>
        <p class="card-desc">...</p>
    </div>
</div>
```

새 작품을 추가할 때 **반드시 할 일**:
1. `.visual-<작품명>` 클래스를 `/* CARDS */` 구역에 신설 (§4 참조 — CSS로만 그린다)
2. `.delay-1` / `.delay-2` / `.delay-3` 중 하나를 부여 (스태거 등장)
3. `.card` 클래스 유지 — **IntersectionObserver 가 이걸로 잡는다** (§7 참조)

---

## 3. 프레임워크 · 빌드

| 항목 | 실제 |
|---|---|
| UI 프레임워크 | **없음.** 바닐라 HTML + DOM API |
| 스타일링 | **없음.** 단일 `<style>` 블록, 순수 CSS |
| 빌드/번들러 | **없음.** `package.json` 조차 없다 |
| 타입스크립트 | **없음** |
| 배포 | 정적 파일 — `index.html` 를 그대로 서빙 |
| JS 패턴 | 즉시실행함수(IIFE)로 스코프 격리 (`:386`, `:403`, `:429`) + 전역 핸들러 |

### 외부 의존성 (CDN 전량)
```html
<!-- :8-9  Google Fonts -->
Inter (300/400/500/600/700) · Playfair Display (400/700, italic)
<!-- :10  Font Awesome 6.4.0 -->
https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css
```

> **npm install 하지 말 것.** 새 의존성이 필요하면 CDN `<link>` / `<script>` 로 추가한다. 빌드 스텝을 도입하는 건 아키텍처 변경이므로 **먼저 사용자에게 물어라.**

### 타이포그래피 역할 분리 (`:29-30`)
```css
body    { font-family:'Inter',sans-serif; line-height:1.6; }
h1,h2,h3,h4 { font-family:'Playfair Display',serif; line-height:1.15; }
```
**제목은 Playfair(세리프), 그 외 전부 Inter.** Figma가 다른 폰트를 지정하면 이 두 개로 매핑하거나, 사용자에게 확인하라.

---

## 4. 애셋 관리 — 가장 중요한 제약

> ### 이 레포에는 이미지 파일이 **단 하나도 없다.**

`git ls-files` 결과는 `index.html` 뿐이다. 모든 비주얼이 **CSS 그라디언트 + canvas** 로 그려져 있다.

```css
/* :81  달 — radial-gradient 3중첩 */
.visual-luna{background:radial-gradient(circle 120px at 50% 38%,rgba(200,180,255,.25) 0%,transparent 70%),...}

/* :88  공장 실루엣 — 다중 배경 레이어로 굴뚝을 그림 */
.factory-silhouette{background:linear-gradient(to top,#0d0500 0%,transparent 100%) 15% 0/18px 130px no-repeat,...}

/* :96  오디오 파형 — JS로 32개 div 생성 (:386-400) */
.wave-bar{width:6px;background:linear-gradient(to top,#0040a0,#00b4d8,#90e0ef);}
```

### Figma 작업 시 규칙

**`download_assets` 를 반사적으로 쓰지 말 것.** 먼저 판단하라:

| Figma 레이어 성격 | 처리 |
|---|---|
| 그라디언트·도형·블러 (장식) | **CSS로 재현한다.** 기존 `.visual-*` 패턴 따라 |
| 단순 아이콘 | **Font Awesome 에 있는지 먼저 확인** (§5) |
| 실제 사진·복잡한 일러스트 | 애셋 추출 필요 → **사용자에게 먼저 확인**. 이 레포의 "애셋 0개" 규약을 깨는 일이다 |

애셋을 정말 들여와야 한다면: 최적화 파이프라인도 CDN 설정도 없으므로, 어디에 두고 어떻게 참조할지 **사용자와 합의한 뒤** 진행한다.

---

## 5. 아이콘 시스템

**Font Awesome 6.4.0, CDN 경유.** 로컬 아이콘 파일 없음, 스프라이트 없음.

```html
<i class="fa-solid fa-chevron-down"></i>      <!-- :203  솔리드 -->
<i class="fa-brands fa-google-drive"></i>     <!-- :263  브랜드 -->
<i class="fa-solid fa-circle-notch fa-spin"></i>  <!-- :443  로딩 스피너 -->
```

### 규약
- 패밀리 접두사 필수: `fa-solid` 또는 `fa-brands`
- 별점은 아이콘 클래스를 `<label>` 자체에 붙이는 특수 패턴 (`:343-347`)

**`aria-hidden` 적용이 일관되지 않다** — 전체 12곳 중 2곳만 붙어 있다:

| 상태 | 줄 |
|---|---|
| ✅ 있음 | `:263`, `:267` |
| ❌ 없음 (마크업) | `:203`, `:309`, `:314`, `:354`, `:365` |
| ❌ 없음 (JS `innerHTML` 주입) | `:443`, `:449`, `:461`, `:473`, `:493` |

> **새로 쓰는 장식 아이콘엔 반드시 `aria-hidden="true"` 를 붙여라.** 기존 것도 해당 줄을 수정하는 김에 고치면 좋다. JS 주입분(`:443` 등)은 버튼 `innerHTML` 문자열 안에 있으니 그 문자열도 같이 고쳐야 한다.

> Figma 아이콘은 **SVG 추출보다 Font Awesome 이름 매칭을 우선**한다. FA 6.4.0 에 없을 때만 인라인 SVG 를 고려하고, 그때도 §4 규칙을 따른다.

---

## 6. 스타일링 방식

### 방법론
CSS Modules / Styled Components / Tailwind **전부 아니다.** 단일 `<style>` 블록 + 플랫 클래스 + CSS 변수.

### 전역 스타일 (`:27-33`)
```css
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;}
html{scroll-behavior:smooth;}
::-webkit-scrollbar{width:4px;}           /* 4px 커스텀 스크롤바 */
```

### 반응형

**유동 타이포 — `clamp()` 선호:**
```css
.hero h1      { font-size:clamp(4.5rem,9vw,8rem); }   /* :55 */
.section-title{ font-size:clamp(2.2rem,4vw,3.5rem); } /* :70 */
```

**브레이크포인트 3개 (전부 `max-width`, 모바일 퍼스트 아님):**

| 폭 | 위치 | 변경 |
|---|---|---|
| `900px` | `:109` | `.system-grid` 2열 → 1열 |
| `768px` | `:167` | 프로젝트 그리드 1열, 섹션 패딩 축소, **nav 링크 숨김**, 푸터 수직 |
| `600px` | `:117` | `.form-row` 2열 → 1열 |

**그리드는 `auto-fit` + `minmax` 로 자동 반응 (`:73`):**
```css
.project-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:28px;}
```

**가로 패딩은 % 단위:** 섹션 `6%` (`:67`), 모바일 `5%` (`:167`)

> 미디어 쿼리를 **해당 컴포넌트 바로 아래**에 두는 패턴(`:109`, `:117`)과 **하단 통합 블록**(`:167`)이 혼재한다. 작은 변경은 컴포넌트 옆에, 레이아웃 전반은 `:167` 블록에 넣어라.

### 단위 규약
- 폰트 크기: `rem` (본문 `.95rem`, 라벨 `.75rem`)
- 간격·라운드: `px`
- 섹션 패딩: `%`
- 투명도: `rgba()` 직접 — `opacity` 토큰 없음

---

## 7. 프로젝트 구조 · 숨은 함정

```
producer-han/
├── index.html          ← 전부 여기 있다 (34KB, 503줄)
├── CLAUDE.md           ← 이 파일
└── obsidian/           ← 리서치 아카이브. 웹사이트와 무관. 건드리지 말 것
```

### 문서 내 섹션 순서
`nav` (:177) → `.hero` (:187) → `#works` (:207) → `#download` (:257) → `#connect` (:272) → `#replyModal` (:363) → `footer` (:373) → `<script>` (:381)

### ⚠️ 함정 1 — 스크롤 등장 애니메이션

`:433` 의 IntersectionObserver 가 **`.card` 와 `.form-panel` 만** 관찰한다:

```js
document.querySelectorAll('.card, .form-panel').forEach(el => obs.observe(el));
```

관련 CSS (`:74-75`)는 **초기 상태가 `opacity:0`** 이다:
```css
.card{opacity:0;transform:translateY(40px);}
.card.visible{opacity:1;transform:translateY(0);}
```

> **Figma에서 가져온 새 섹션에 `.card`/`.form-panel` 클래스가 없고 `opacity:0` 스타일을 복사해 오면 → 영구히 안 보인다.**
> 새 컴포넌트를 등장 애니메이션에 넣으려면 `:433` 의 셀렉터에 클래스를 추가하거나, 두 클래스 중 하나를 재사용하라.

### ⚠️ 함정 2 — 스태거 딜레이 유틸 (`:169-172`)
```css
.delay-1{transition-delay:.1s!important;}
.delay-2{transition-delay:.22s!important;}
.delay-3{transition-delay:.34s!important;}
.delay-fp2{transition-delay:.15s!important;}
```
`!important` 가 붙어 있다. **4개뿐이므로** 카드를 4개 이상 추가하면 `.delay-4` 를 직접 만들어야 한다.

### ⚠️ 함정 3 — 미설정 외부 연동

둘 다 플레이스홀더 상태이고, **플레이스홀더를 감지해 성공 UI를 가짜로 띄우는 폴백 로직이 있다**:

| 연동 | 플레이스홀더 | 폴백 |
|---|---|---|
| Formspree | `action="...f/YOUR_FORM_ID"` (`:289`) | `:446-451` — 모달 띄우고 종료 |
| Google Apps Script | `APPS_SCRIPT_URL = 'YOUR_GOOGLE_...'` (`:383`) | `:476-481` — 성공 배너 표시 |

> 폼 UI를 리디자인할 때 **이 폴백 분기를 깨지 말 것.** 설정 가이드가 HTML 주석(`:283-288`, `:324-339`)에 들어 있으니 함께 유지하라.

### ⚠️ 함정 4 — 하드코딩된 개인정보
연락처 `k333896@naver.com` 이 `:282`, `:377` 두 곳에, Google Drive 링크가 `:266`, `:308` 에 있다. 리팩터링 중 유실시키지 말 것.

---

## 8. Figma 통합 체크리스트

디자인을 가져올 때 순서대로:

- [ ] `get_design_context` 출력의 **React/Tailwind를 버린다**
- [ ] 레이아웃 값(간격·크기·라운드)만 추출
- [ ] 색을 §1 매핑표로 **CSS 변수에 매핑** — 하드코딩 금지
- [ ] 폰트를 **Inter / Playfair Display** 로 매핑
- [ ] 아이콘을 **Font Awesome 이름**으로 매칭 (§5)
- [ ] 장식 그라디언트는 **CSS로 재현**, 애셋 추출 금지 (§4)
- [ ] 클래스명을 **`블록-요소` 플랫 패턴**으로 작성 (§2)
- [ ] variant 는 **추가 클래스**로 (`.btn .btn-outline`)
- [ ] `index.html` 의 **해당 주석 구역**에 CSS 삽입 (§2)
- [ ] 등장 애니메이션 필요시 **`:433` 셀렉터 확인** (함정 1)
- [ ] 브레이크포인트 **768 / 900 / 600** 에서 확인 (§6)
- [ ] 브라우저로 직접 열어 확인 — **빌드 스텝이 없으니 즉시 반영된다**

### 하기 전에 반드시 물어볼 것
- 빌드 시스템 / npm / 프레임워크 도입
- 파일 분할 (`index.html` 단일 파일 깨기)
- 래스터 애셋 도입 (§4)
- 토큰 13개 체계 확장
