---
name: s5 skill store cache
overview: S5-1 根治 skill_store 缓存失效契约:签名由 max-mtime 改为路径集合+mtime/size(侦测增删改)、promote/approve 写后 invalidate。让 promoted qa_rule 写后可靠可见,两个 flaky 测试因被测代码变可靠而真实转绿,无需改测试。一刀完成。
todos:
  - id: s5-1-cache-contract
    content: S5-1 skill_store 缓存失效契约 [已完成]:store.py 签名由 max-mtime 改为 dir_mtime + (相对路径,mtime,size) 排序稳定元组,绕开同-tick mtime 盲区;skill_promotion/__init__.py promote_approved_candidate 写盘成功后调 get_skill_store().invalidate() 修生产 approve 可见性 bug。不改 promoted smoke 断言。提交 80ffccf。
    status: completed
  - id: s5-1-verify
    content: 验证 [已完成]:新增 test_skill_store 单测(空目录 scan→写文件→再 scan 必见 + promote 后 invalidate 可见);2 个 promoted smoke 测试连续 3 轮均 2 passed;docker full pytest tests = 256 passed。原子提交 80ffccf。
    status: completed
  - id: s5-1-wrapup
    content: 收尾 [已完成]:回写总纲 S5→completed、§4.9 记缓存失效契约与测试转稳证据;S0-S5 全阶段收官。
    status: completed
isProject: false
---

# S5-1 skill_store 缓存失效契约(一刀)

## 第一性原理:问题就是"写了 skill 读不到"

两个 flaky 测试(`test_promoted_qa_rule_blocks_then_writer_redo_passes` / `test_promoted_qa_rule_blocks_report_with_enforced_yaml`,[test_smoke.py](backend/app/tests/test_smoke.py))间歇失败,根因已确证为 [store.py](backend/app/service/skill_store/store.py) 的缓存失效有两个直接缺陷:

- **签名只认 max-mtime**([store.py](backend/app/service/skill_store/store.py):23-29):`_skills_dir_signature()` 返回所有 mtime 的 max(单个 float)。"空目录 scan → 同一 mtime tick 内写 SKILL.md → 再 scan"时,新签名可能 == 旧签名 → `_ensure_scanned()`(37-41) no-op,`skill_count` 永远=0。
- **promote 写后不失效**:promote/approve 经 [writers.py](backend/app/service/skill_promotion/writers.py) 原子写 `SKILL.md` 后,全链路**无 `invalidate()`/scan**(`invalidate()` 已存在于 store.py:31-35,但仅测试调用)。这是生产 bug——approve 一个 qa_rule 后立即 run,QA 因 mtime 缓存看不到新 rule、静默不 enforcement。

修好这两点,promoted rule 写后可靠可见,enforcement 正常跑,测试真实转绿。**不动测试断言/setup、不加任何 mock**——这是"修生产不修测试"的最强验证。

## 改动(C 方案:签名增强 + 写侧 invalidate)

### 1. 签名增强(侦测增删改) — [store.py](backend/app/service/skill_store/store.py):23-29

`_skills_dir_signature()` 由"单个 max-mtime"改为对所有 `SKILL.md` 的 **(相对路径, mtime, size)** 排序后的稳定元组(连同 `skills_dir` mtime):

- 空目录 → `(dir_mtime, ())`;写入一个文件 → `(dir_mtime', (("qa_rule/x/SKILL.md", mt, sz),))`。路径集合 `()→1 项` 使签名必变,**绕开同 tick mtime 盲区**。
- `size` 兜住"同名覆盖、mtime 未变"的极边缘(promote atomic replace 同名时)。
- `_ensure_scanned()`(37-41) / `_skills_dir_mtime` 字段类型随之由 `float|None` 调整为签名元组类型(改类型注解,语义不变)。

### 2. promote/approve 写后 invalidate — 生产正确性

写 `SKILL.md` 完成后显式失效单例缓存(清 metadata + content cache,语义清晰、并兜住 mtime 不变改写):

- 落点优先在编排层 [skill_promotion/__init__.py](backend/app/service/skill_promotion/__init__.py):166-194 `promote_approved_candidate` 写盘成功后调 `get_skill_store().invalidate()`(谁写谁失效);确认该函数是 approve 的唯一 promote 入口([skill_rt.py](backend/app/router/skill_rt.py):139-183)。
- 注意 store 单例的 `skills_dir` 与 promote 的 `skills_root` 一致性(测试 patch 的是同一实例属性,生产同指 `backend/skills`)。

## 验证(不改测试)

- 重复跑那 2 个 smoke 测试多次确认**稳定转绿、不再 flaky**。
- docker full `pytest tests -q`:目标 254 passed / 0 failed(S5-1 两个从 flaky 转为稳定通过)。
- 新增针对签名的单测(test_skill_store):空目录 scan → 写文件 → 再 scan 必见新 skill(覆盖同 tick 场景);promote 路径写后 store 可见。
- 原子提交。

## 收尾

二级 plan 无误后回写一级总纲:`S5`→completed,§4 记录"skill_store 缓存失效契约(路径集合签名 + 写侧 invalidate)"与两个测试转稳证据。S5 收口即 S0-S5 全阶段完成,系统纠偏总纲收官。

## 执行收尾

S5-1 已落地。提交:`80ffccf`。验证:`test_skill_store.py test_skill_promotion_router.py` = **7 passed**;两个 promoted smoke 测试连续 3 轮均 **2 passed**;docker 全量 `pytest tests` = **256 passed**。staged secret scan 通过。S0-S5 全阶段完成。

## 不做(YAGNI / 避免过度设计)

- 不加 QA promoted enforcement 降级可观测(count=0 warning/metric):运行时无法区分"本就无 promoted rule"与"该有却没加载",根因修复后 count 不再=0,该路径不再触发。
- 不改两个测试的断言/setup,不加 mock 绕过真实 enforcement。
- 不引入文件监听/inotify 等重型机制(skill 写入低频,签名+invalidate 足够)。
