# Qualitative localization cases

Cases are deterministically selected (lexicographically first three matching instances per category).

## path cue helps — `Hannah-Sten__TeXiFy-IDEA-2935`

- Language/repository: kotlin / `TeXiFy-IDEA`
- Gold: `['src/nl/hannahsten/texifyidea/inspections/latex/codematurity/LatexPrimitiveStyleInspection.kt', 'src/nl/hannahsten/texifyidea/util/magic/CommandMagic.kt']`
- Explicit gold-path cues: `['src/nl/hannahsten/texifyidea/inspections/latex/codematurity/LatexPrimitiveStyleInspection.kt']`
- Query excerpt: "Convert to LaTeX alternative" command unexpectedly rearranged text and caused a NullPointerException ### Type of JetBrains IDE (IntelliJ, PyCharm, etc.) and version PyCharm 2022.3.1 (build PY-223.8214.51) ### Operating System Windows 11 10.0 (amd64) ### TeXiFy IDEA version 0.7.25.1 ### Description I used the command to convert primitive \bf to \textbf. It produced a NullPointerException with the 
- BM25 top-3: `['src/nl/hannahsten/texifyidea/action/library/SyncLibraryAction.kt', 'src/nl/hannahsten/texifyidea/action/library/AddLibraryAction.kt', 'src/nl/hannahsten/texifyidea/inspections/latex/probablebugs/packages/LatexPackageNotInstalledInspection.kt']`
- Path-anchor top-3: `['src/nl/hannahsten/texifyidea/inspections/latex/codematurity/LatexPrimitiveStyleInspection.kt', 'src/nl/hannahsten/texifyidea/action/library/SyncLibraryAction.kt', 'src/nl/hannahsten/texifyidea/action/library/AddLibraryAction.kt']`
- Graph top-3: `['src/nl/hannahsten/texifyidea/action/library/SyncLibraryAction.kt', 'src/nl/hannahsten/texifyidea/action/library/AddLibraryAction.kt', 'src/nl/hannahsten/texifyidea/inspections/latex/probablebugs/packages/LatexPackageNotInstalledInspection.kt']`

## path cue helps — `ankidroid__Anki-Android-19661`

- Language/repository: kotlin / `Anki-Android`
- Gold: `['AnkiDroid/src/main/java/com/ichi2/anki/AnkiDroidApp.kt']`
- Explicit gold-path cues: `['AnkiDroid/src/main/java/com/ichi2/anki/AnkiDroidApp.kt']`
- Query excerpt: [BUG]: startup crash - getExternalFilesDir unexpectedly returned null. Media state: removed 2.23.0beta3 * `getExternalFilesDir` is null * Collection path is set * `CollectionHelper.initializeAnkiDroidDirectory` throws `StorageAccessException` https://ankidroid.org/acra/app/1/bug/362178/report/968c2402-f20d-4984-b5b5-3781a4feb340 ``` java.lang.RuntimeException: Unable to create application com.ichi
- BM25 top-3: `['AnkiDroid/src/main/java/com/ichi2/anki/CollectionHelper.kt', 'AnkiDroid/src/main/java/com/ichi2/anki/AnkiDroidApp.kt', 'AnkiDroid/src/main/java/com/ichi2/anki/servicelayer/ScopedStorageService.kt']`
- Path-anchor top-3: `['AnkiDroid/src/main/java/com/ichi2/anki/AnkiDroidApp.kt', 'AnkiDroid/src/main/java/com/ichi2/anki/CollectionHelper.kt', 'AnkiDroid/src/main/java/com/ichi2/anki/exception/SystemStorageException.kt']`
- Graph top-3: `['AnkiDroid/src/main/java/com/ichi2/anki/CollectionHelper.kt', 'AnkiDroid/src/main/java/com/ichi2/anki/AnkiDroidApp.kt', 'AnkiDroid/src/main/java/com/ichi2/anki/servicelayer/ScopedStorageService.kt']`

## path cue helps — `apache__dubbo-7041`

- Language/repository: java / `dubbo`
- Gold: `['dubbo-common/src/main/java/org/apache/dubbo/common/utils/ReflectUtils.java']`
- Explicit gold-path cues: `['dubbo-common/src/main/java/org/apache/dubbo/common/utils/ReflectUtils.java']`
- Query excerpt: Unable to refer interface with CompletableFuture<T> ### Environment * Dubbo version: 2.7.8 * Java version: jdk 11 ### Steps to reproduce this issue 1. Define a interface like this: ``` java public interface TypeClass<T> { CompletableFuture<T> getGenericFuture(); } ``` 2. Refer or export it 3. Detail log ``` java.lang.ClassCastException: class sun.reflect.generics.reflectiveObjects.TypeVariableImpl
- BM25 top-3: `['dubbo-rpc/dubbo-rpc-api/src/main/java/org/apache/dubbo/rpc/filter/GenericImplFilter.java', 'dubbo-common/src/main/java/org/apache/dubbo/common/beanutil/JavaBeanSerializeUtil.java', 'dubbo-rpc/dubbo-rpc-xml/src/main/java/org/apache/dubbo/xml/rpc/protocol/xmlrpc/XmlRpcProxyFactoryBean.java']`
- Path-anchor top-3: `['dubbo-common/src/main/java/org/apache/dubbo/common/utils/ReflectUtils.java', 'dubbo-common/src/main/java/org/apache/dubbo/config/annotation/Method.java', 'dubbo-rpc/dubbo-rpc-api/src/main/java/org/apache/dubbo/rpc/filter/GenericImplFilter.java']`
- Graph top-3: `['dubbo-common/src/main/java/org/apache/dubbo/common/beanutil/JavaBeanSerializeUtil.java', 'dubbo-common/src/main/java/org/apache/dubbo/common/utils/ReflectUtils.java', 'dubbo-common/src/main/java/org/apache/dubbo/common/utils/PojoUtils.java']`

## non-gold path cue misleads — `catchorg__Catch2-2288`

- Language/repository: cpp / `Catch2`
- Gold: `['include/internal/catch_approx.h']`
- Explicit gold-path cues: `[]`
- Query excerpt: Approx::operator() not const-correct **Describe the bug** The `Approx` type has an overload of `template <typename T, ...SFINAE...> Approx operator()(T const&)` which (correct me if I'm wrong) is meant to be a factory function for instances that have the same epsilon, margin, and scale, but that use the passed value. AFAICT this should be const on the instance, but it's not. Minimum failing exampl
- BM25 top-3: `['include/internal/catch_approx.h', 'include/internal/catch_approx.cpp', 'include/internal/catch_matchers_vector.h']`
- Path-anchor top-3: `['single_include/catch2/catch.hpp', 'include/catch.hpp', 'include/internal/catch_approx.h']`
- Graph top-3: `['include/internal/catch_approx.h', 'single_include/catch2/catch.hpp', 'include/internal/catch_approx.cpp']`

## non-gold path cue misleads — `clap-rs__clap-2773`

- Language/repository: rust / `clap`
- Gold: `['src/output/help.rs']`
- Explicit gold-path cues: `[]`
- Query excerpt: Very large display_order values cause a crash while displaying help ### Please complete the following tasks - [X] I have searched the [discussions](https://github.com/clap-rs/clap/discussions) - [X] I have searched the existing issues ### Rust Version rustc 1.55.0 (c8dfcfe04 2021-09-06) ### Clap Version 3.0.0-beta.4 ### Minimal reproducible code ```rust fn main() { clap::App::new("test") .subcomma
- BM25 top-3: `['src/output/help.rs', 'src/build/app/settings.rs', 'src/output/usage.rs']`
- Path-anchor top-3: `['clap_up/src/lib.rs', 'clap_generate/src/lib.rs', 'src/lib.rs']`
- Graph top-3: `['src/parse/validator.rs', 'src/parse/errors.rs', 'clap_derive/src/parse.rs']`

## non-gold path cue misleads — `clap-rs__clap-3311`

- Language/repository: rust / `clap`
- Gold: `['src/build/app/mod.rs']`
- Explicit gold-path cues: `[]`
- Query excerpt: debug_assert fails with PropagateVersion in 3.0.8/3.0.9, but get_matches does not ### Please complete the following tasks - [X] I have searched the [discussions](https://github.com/clap-rs/clap/discussions) - [X] I have searched the existing issues ### Rust Version rustc 1.57.0 (f1edd0429 2021-11-29) ### Clap Version 3.0.9 ### Minimal reproducible code ```rust fn cli() -> clap::App<'static> { clap
- BM25 top-3: `['src/build/app/mod.rs', 'src/build/app/settings.rs', 'src/build/app/debug_asserts.rs']`
- Path-anchor top-3: `['src/build/app/debug_asserts.rs', 'src/build/arg/debug_asserts.rs', 'src/build/app/mod.rs']`
- Graph top-3: `['src/build/app/debug_asserts.rs', 'src/build/app/mod.rs', 'src/build/arg/mod.rs']`

## graph expansion hurts — `BurntSushi__ripgrep-1367`

- Language/repository: rust / `ripgrep`
- Gold: `['grep-regex/src/literal.rs']`
- Explicit gold-path cues: `['grep-regex/src/literal.rs']`
- Query excerpt: match bug ``` $ rg --version ripgrep 11.0.1 (rev 7bf7ceb5d3) -SIMD -AVX (compiled) +SIMD +AVX (runtime) ``` This matches: ``` $ echo 'CCAGCTACTCGGGAGGCTGAGGCTGGAGGATCGCTTGAGTCCAGGAGTTC' | egrep 'CCAGCTACTCGGGAGGCTGAGGCTGGAGGATCGCTTGAGTCCAGGAG[ATCG]{2}C' CCAGCTACTCGGGAGGCTGAGGCTGGAGGATCGCTTGAGTCCAGGAGTTC ``` But this doesn't: ``` $ echo 'CCAGCTACTCGGGAGGCTGAGGCTGGAGGATCGCTTGAGTCCAGGAGTTC' | rg 'CCA
- BM25 top-3: `['grep-regex/src/literal.rs', 'src/app.rs', 'grep-regex/src/matcher.rs']`
- Path-anchor top-3: `['grep-regex/src/literal.rs', 'grep-regex/src/matcher.rs', 'grep-pcre2/src/matcher.rs']`
- Graph top-3: `['src/app.rs', 'src/args.rs', 'globset/src/lib.rs']`

## graph expansion hurts — `alibaba__fastjson2-2097`

- Language/repository: java / `fastjson2`
- Gold: `['core/src/main/java/com/alibaba/fastjson2/reader/ObjectReaderImplList.java']`
- Explicit gold-path cues: `[]`
- Query excerpt: [BUG] reference in java.util.Arrays$ArrayList(CLASS_ARRAYS_LIST) deserialization wrong ### 问题描述 当反序列化对象为 java.util.Arrays$ArrayList 类型 (Kotlin 中的 listOf(...) 等同)，且列表中存在 reference 元素的情况下, 该对象反序列化时其列表中的所有 reference 元素都为 null ### 环境信息 - OS信息： [e.g.：CentOS 8.4.2105 4Core 3.10GHz 16 GB] - JDK信息： [e.g.：Openjdk 1.8.0_312] - 版本信息：Fastjson2 2.0.43 ### 重现步骤 https://github.com/xtyuns/sample-e202312131-fastjs
- BM25 top-3: `['core/src/main/java/com/alibaba/fastjson2/reader/ObjectReaderImplList.java', 'fastjson1-compatible/src/main/java/com/alibaba/fastjson/TypeReference.java', 'fastjson1-compatible/src/main/java/com/alibaba/fastjson/support/jaxrs/FastJsonProvider.java']`
- Path-anchor top-3: `['core/src/main/java/com/alibaba/fastjson2/reader/ObjectReaderImplList.java', 'fastjson1-compatible/src/main/java/com/alibaba/fastjson/TypeReference.java', 'fastjson1-compatible/src/main/java/com/alibaba/fastjson/support/jaxrs/FastJsonProvider.java']`
- Graph top-3: `['fastjson1-compatible/src/main/java/com/alibaba/fastjson/support/jaxrs/FastJsonProvider.java', 'core/src/main/java/com/alibaba/fastjson2/JSONReader.java', 'core/src/main/java/com/alibaba/fastjson2/reader/ObjectReaderImplList.java']`

## graph expansion hurts — `anuraghazra__github-readme-stats-1041`

- Language/repository: js / `github-readme-stats`
- Gold: `['src/cards/wakatime-card.js']`
- Explicit gold-path cues: `[]`
- Query excerpt: [Bug] wakatime langs_count is invalid when layout=compact **Describe the bug** wakatime langs_count is invalid when layout=compact, **it does work when i don't make layout=compact.** As follows, i make langs_count=6 and layout=compact, but it's invalid. **Screenshots** ![image](https://user-images.githubusercontent.com/41513919/116766616-fe4be800-aa5d-11eb-804d-bb51376a1d1a.png)
- BM25 top-3: `['src/cards/wakatime-card.js', 'src/cards/top-languages-card.js', 'api/wakatime.js']`
- Path-anchor top-3: `['src/cards/wakatime-card.js', 'src/cards/top-languages-card.js', 'api/wakatime.js']`
- Graph top-3: `['src/common/utils.js', 'api/top-langs.js', 'src/fetchers/stats-fetcher.js']`

## graph expansion helps — `BurntSushi__ripgrep-723`

- Language/repository: rust / `ripgrep`
- Gold: `['complete/_rg', 'doc/rg.1', 'doc/rg.1.md', 'src/app.rs', 'src/args.rs', 'src/printer.rs']`
- Explicit gold-path cues: `[]`
- Query excerpt: Fixed width line numbers It would be nice to be able to see the indentation level of searched text line up. One way to do this would be to have fixed width line numbers in search results. This could be accomplished through an option flag and left-padding with either spaces or zeroes when the flag is active. As this is primarily of interest for matches within a file, only the matches within a file 
- BM25 top-3: `['globset/src/glob.rs', 'src/app.rs', 'src/args.rs']`
- Path-anchor top-3: `['globset/src/glob.rs', 'src/app.rs', 'src/args.rs']`
- Graph top-3: `['src/args.rs', 'ignore/src/types.rs', 'src/search_stream.rs']`

## graph expansion helps — `BurntSushi__ripgrep-727`

- Language/repository: rust / `ripgrep`
- Gold: `['src/args.rs']`
- Explicit gold-path cues: `[]`
- Query excerpt: Suggest --fixed-strings on invalid regexps ``` $ rg "foo(" Error parsing regex near 'foo(' at character offset 3: Unclosed parenthesis. ``` I think ripgrep should suggest the `--fixed-strings` argument if there's a regex syntax error.
- BM25 top-3: `['src/app.rs', 'src/args.rs', 'globset/src/lib.rs']`
- Path-anchor top-3: `['src/app.rs', 'src/args.rs', 'globset/src/lib.rs']`
- Graph top-3: `['src/args.rs', 'ignore/src/dir.rs', 'src/app.rs']`

## graph expansion helps — `alibaba__fastjson2-2559`

- Language/repository: java / `fastjson2`
- Gold: `['core/src/main/java/com/alibaba/fastjson2/util/TypeUtils.java']`
- Explicit gold-path cues: `[]`
- Query excerpt: [FEATURE]org.bson.types.Decimal128转Double时会报错 ### 请描述您的需求或者改进建议 背景如下： 1、我们会把`java`对象通过`fastjson`转为`String`然后通过**MQ** 发送出来，在接收端会再通过`fastjson`把`String`转化`JSONObject` ``` public void handleChannel(String data) throws PropertyMapperException { JSONObject jsonData = JSON.parseObject(data); ViewMO inputMO = jsonData.toJavaObject(ViewMO.class); ImportBatchDetailDO task = new ImportBatchDetailDO(); task.s
- BM25 top-3: `['fastjson1-compatible/src/main/java/com/alibaba/fastjson/JSONObject.java', 'core/src/main/java/com/alibaba/fastjson2/util/TypeUtils.java', 'core/src/main/java/com/alibaba/fastjson2/support/LambdaMiscCodec.java']`
- Path-anchor top-3: `['fastjson1-compatible/src/main/java/com/alibaba/fastjson/JSONObject.java', 'core/src/main/java/com/alibaba/fastjson2/util/TypeUtils.java', 'core/src/main/java/com/alibaba/fastjson2/support/LambdaMiscCodec.java']`
- Graph top-3: `['core/src/main/java/com/alibaba/fastjson2/util/TypeUtils.java', 'fastjson1-compatible/src/main/java/com/alibaba/fastjson/JSONArray.java', 'fastjson1-compatible/src/main/java/com/alibaba/fastjson/util/TypeUtils.java']`

