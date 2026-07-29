[CmdletBinding()]
param(
    [string]$RepoRoot,
    [switch]$SelfTest
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

function Add-ValidationIssue {
    param(
        [System.Collections.Generic.List[object]]$Issues,
        [string]$Code,
        [string]$Path,
        [string]$Message
    )

    [void]$Issues.Add([PSCustomObject]@{
        Code = $Code
        Path = $Path
        Message = $Message
    })
}

function Get-Utf8Text {
    param([string]$Path)

    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

function Get-SkillFrontmatter {
    param([string]$Path)

    $content = Get-Utf8Text -Path $Path
    $match = [regex]::Match(
        $content,
        '\A---\r?\n(?<frontmatter>.*?)\r?\n---(?:\r?\n|$)',
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
    if (-not $match.Success) {
        return $null
    }

    $fields = [ordered]@{}
    foreach ($line in ($match.Groups['frontmatter'].Value -split '\r?\n')) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith('#')) {
            continue
        }
        $fieldMatch = [regex]::Match($line, '^(?<key>[A-Za-z0-9-]+):\s*(?<value>.*)$')
        if (-not $fieldMatch.Success) {
            return $null
        }
        $key = $fieldMatch.Groups['key'].Value
        $value = $fieldMatch.Groups['value'].Value.Trim().Trim('"').Trim("'")
        $fields[$key] = $value
    }

    return [PSCustomObject]@{
        Fields = $fields
        Content = $content
    }
}

function Test-RequiredText {
    param(
        [System.Collections.Generic.List[object]]$Issues,
        [string]$Path,
        [string[]]$RequiredPatterns,
        [string]$Code
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $content = Get-Utf8Text -Path $Path
    foreach ($pattern in $RequiredPatterns) {
        if ($content -notmatch $pattern) {
            Add-ValidationIssue -Issues $Issues -Code $Code -Path $Path -Message "Missing required pattern: $pattern"
        }
    }
}

function Invoke-RepoValidation {
    param([string]$Root)

    $issues = New-Object 'System.Collections.Generic.List[object]'
    $resolvedRoot = $null
    try {
        $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    }
    catch {
        Add-ValidationIssue -Issues $issues -Code 'REPO_MISSING' -Path $Root -Message 'Repository root does not exist.'
        return $issues
    }

    $requiredRootFiles = @(
        'README.md',
        'LICENSE',
        'VERSION',
        'CHANGELOG.md',
        '.gitignore',
        'tools\build.ps1',
        '.github\workflows\validate.yml'
    )
    foreach ($relativePath in $requiredRootFiles) {
        $fullPath = Join-Path $resolvedRoot $relativePath
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            Add-ValidationIssue -Issues $issues -Code 'ROOT_FILE_MISSING' -Path $relativePath -Message 'Required repository file is missing.'
        }
    }

    $versionPath = Join-Path $resolvedRoot 'VERSION'
    if (Test-Path -LiteralPath $versionPath -PathType Leaf) {
        $version = (Get-Utf8Text -Path $versionPath).Trim()
        if ($version -notmatch '^\d+\.\d+\.\d+$') {
            Add-ValidationIssue -Issues $issues -Code 'VERSION_INVALID' -Path 'VERSION' -Message 'VERSION must use x.y.z syntax.'
        }
    }

    $readmePath = Join-Path $resolvedRoot 'README.md'
    Test-RequiredText -Issues $issues -Path $readmePath -Code 'README_CONTENT' -RequiredPatterns @(
        'Source Available',
        'Not Open Source',
        '\$sgs-mece',
        '/skill:sgs-mece',
        [regex]::Escape('作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)'),
        [regex]::Escape('Built by  [@xstevenzhang](https://x.com/xstevenzhang)')
    )

    $licensePath = Join-Path $resolvedRoot 'LICENSE'
    Test-RequiredText -Issues $issues -Path $licensePath -Code 'LICENSE_CONTENT' -RequiredPatterns @(
        'SGSkills Internal Use License 1\.0',
        'Source Available',
        'Not Open Source',
        '个人学习',
        '自身电商经营',
        '内部修改',
        '公开再分发',
        '转售',
        '白标',
        '付费课程',
        '不构成法律意见'
    )

    $gitignorePath = Join-Path $resolvedRoot '.gitignore'
    Test-RequiredText -Issues $issues -Path $gitignorePath -Code 'GITIGNORE_CONTENT' -RequiredPatterns @(
        '(?m)^/dist/$',
        '(?m)^/\.work/$'
    )

    $changelogPath = Join-Path $resolvedRoot 'CHANGELOG.md'
    Test-RequiredText -Issues $issues -Path $changelogPath -Code 'CHANGELOG_CONTENT' -RequiredPatterns @(
        '1\.4\.0'
    )

    $skillsRoot = Join-Path $resolvedRoot 'skills'
    if (-not (Test-Path -LiteralPath $skillsRoot -PathType Container)) {
        Add-ValidationIssue -Issues $issues -Code 'SKILLS_ROOT_MISSING' -Path 'skills' -Message 'skills directory is missing.'
    }
    else {
        $skillDirs = @(Get-ChildItem -LiteralPath $skillsRoot -Directory)
        if ($skillDirs.Count -eq 0) {
            Add-ValidationIssue -Issues $issues -Code 'SKILL_MISSING' -Path 'skills' -Message 'At least one real skill directory is required.'
        }

        foreach ($skillDir in $skillDirs) {
            $skillRelative = "skills\$($skillDir.Name)"
            $skillFile = Join-Path $skillDir.FullName 'SKILL.md'
            if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
                Add-ValidationIssue -Issues $issues -Code 'SKILL_FILE_MISSING' -Path $skillRelative -Message 'SKILL.md is required.'
                continue
            }

            $disallowedRuntimeFiles = @('README.md', 'QUICKREF.md', 'CHANGELOG.md')
            foreach ($fileName in $disallowedRuntimeFiles) {
                if (Test-Path -LiteralPath (Join-Path $skillDir.FullName $fileName)) {
                    Add-ValidationIssue -Issues $issues -Code 'RUNTIME_DOC_PRESENT' -Path "$skillRelative\$fileName" -Message 'Repository documentation must not live in the runtime skill.'
                }
            }
            if (Test-Path -LiteralPath (Join-Path $skillDir.FullName 'KNOWLEDGE')) {
                Add-ValidationIssue -Issues $issues -Code 'LEGACY_DIRECTORY' -Path "$skillRelative\KNOWLEDGE" -Message 'Use the standard references directory.'
            }

            $allowedRootNames = @('SKILL.md', 'agents', 'references', 'scripts', 'assets')
            foreach ($item in (Get-ChildItem -LiteralPath $skillDir.FullName -Force)) {
                if ($allowedRootNames -notcontains $item.Name) {
                    Add-ValidationIssue -Issues $issues -Code 'RUNTIME_ITEM_UNEXPECTED' -Path "$skillRelative\$($item.Name)" -Message 'Unexpected item in runtime skill root.'
                }
            }

            $frontmatter = Get-SkillFrontmatter -Path $skillFile
            if ($null -eq $frontmatter) {
                Add-ValidationIssue -Issues $issues -Code 'FRONTMATTER_INVALID' -Path "$skillRelative\SKILL.md" -Message 'Frontmatter is missing or cannot be parsed.'
                continue
            }

            $allowedKeys = @('name', 'description', 'license')
            foreach ($key in $frontmatter.Fields.Keys) {
                if ($allowedKeys -notcontains $key) {
                    Add-ValidationIssue -Issues $issues -Code 'FRONTMATTER_KEY' -Path "$skillRelative\SKILL.md" -Message "Unexpected frontmatter key: $key"
                }
            }
            foreach ($requiredKey in $allowedKeys) {
                if (-not $frontmatter.Fields.Contains($requiredKey) -or [string]::IsNullOrWhiteSpace($frontmatter.Fields[$requiredKey])) {
                    Add-ValidationIssue -Issues $issues -Code 'FRONTMATTER_REQUIRED' -Path "$skillRelative\SKILL.md" -Message "Missing required frontmatter key: $requiredKey"
                }
            }

            if ($frontmatter.Fields.Contains('name')) {
                $name = [string]$frontmatter.Fields['name']
                if ($name -notmatch '^[a-z0-9]+(?:-[a-z0-9]+)*$' -or $name -ne $skillDir.Name) {
                    Add-ValidationIssue -Issues $issues -Code 'SKILL_NAME' -Path "$skillRelative\SKILL.md" -Message 'name must be kebab-case and equal the directory name.'
                }
            }
            if ($frontmatter.Fields.Contains('description')) {
                $description = [string]$frontmatter.Fields['description']
                if ($description.Length -gt 1024 -or $description -notmatch '^Use when ') {
                    Add-ValidationIssue -Issues $issues -Code 'DESCRIPTION_FORMAT' -Path "$skillRelative\SKILL.md" -Message 'description must start with "Use when " and be at most 1024 characters.'
                }
                if ($description -notmatch '电商' -or $description -notmatch '边界不清|跨模块|模糊' -or $description -notmatch '不适用|已有明确|不要') {
                    Add-ValidationIssue -Issues $issues -Code 'DESCRIPTION_BOUNDARY' -Path "$skillRelative\SKILL.md" -Message 'description must include ecommerce triggers, ambiguous/cross-module scope, and an anti-trigger.'
                }
            }

            $relativeReferences = [regex]::Matches(
                $frontmatter.Content,
                '(?<path>(?:references|scripts|assets)/[A-Za-z0-9._/-]+)'
            ) | ForEach-Object { $_.Groups['path'].Value } | Sort-Object -Unique
            foreach ($relativeReference in $relativeReferences) {
                $platformPath = $relativeReference.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
                if (-not (Test-Path -LiteralPath (Join-Path $skillDir.FullName $platformPath) -PathType Leaf)) {
                    Add-ValidationIssue -Issues $issues -Code 'REFERENCE_MISSING' -Path "$skillRelative\SKILL.md" -Message "Referenced file does not exist: $relativeReference"
                }
            }

            foreach ($requiredReference in @('frameworks.md', 'mece-principles.md', 'questions.md')) {
                $referencePath = Join-Path (Join-Path $skillDir.FullName 'references') $requiredReference
                if (-not (Test-Path -LiteralPath $referencePath -PathType Leaf)) {
                    Add-ValidationIssue -Issues $issues -Code 'REFERENCE_REQUIRED' -Path "$skillRelative\references\$requiredReference" -Message 'Required reference file is missing.'
                }
            }

            $openaiYaml = Join-Path $skillDir.FullName 'agents\openai.yaml'
            Test-RequiredText -Issues $issues -Path $openaiYaml -Code 'OPENAI_YAML_CONTENT' -RequiredPatterns @(
                [regex]::Escape('display_name: "sgs-mece｜电商运营问题结构化拆解顾问"'),
                'short_description:',
                'allow_implicit_invocation:\s*true'
            )
            if (-not (Test-Path -LiteralPath $openaiYaml -PathType Leaf)) {
                Add-ValidationIssue -Issues $issues -Code 'OPENAI_YAML_MISSING' -Path "$skillRelative\agents\openai.yaml" -Message 'Codex interface metadata is required.'
            }
        }
    }

    $scanFiles = @(
        Get-ChildItem -LiteralPath $resolvedRoot -Recurse -File |
            Where-Object {
                $_.Extension -in @('.md', '.yaml', '.yml') -and
                $_.FullName -notmatch '\\\.work\\|\\tests\\|\\dist\\|\\\.git\\'
            }
    )
    foreach ($file in $scanFiles) {
        $relative = $file.FullName.Substring($resolvedRoot.Length).TrimStart('\')
        $content = Get-Utf8Text -Path $file.FullName
        foreach ($banned in @('麦肯锡 MECE 原则', '理论原典', '每个框架均满足 MECE', '5问', '⭐⭐')) {
            if ($content.Contains($banned)) {
                Add-ValidationIssue -Issues $issues -Code 'BANNED_PHRASE' -Path $relative -Message "Banned or unsupported phrase found: $banned"
            }
        }
        if ($content -match '麦肯锡|McKinsey') {
            $allowedSource = $relative -eq 'skills\sgs-mece\references\mece-principles.md'
            if (-not $allowedSource) {
                Add-ValidationIssue -Issues $issues -Code 'MCKINSEY_SCOPE' -Path $relative -Message 'McKinsey may appear only in the historical source note.'
            }
        }
    }

    $principlesPath = Join-Path $resolvedRoot 'skills\sgs-mece\references\mece-principles.md'
    if (Test-Path -LiteralPath $principlesPath -PathType Leaf) {
        $principles = Get-Utf8Text -Path $principlesPath
        if ($principles -notmatch 'Barbara Minto' -or
            $principles -notmatch 'https://www\.mckinsey\.com/alumni/news-and-events/global-news/alumni-news/barbara-minto-mece-i-invented-it-so-i-get-to-say-how-to-pronounce-it' -or
            $principles -notmatch '无隶属.*合作.*背书') {
            Add-ValidationIssue -Issues $issues -Code 'SOURCE_NOTE' -Path 'skills\sgs-mece\references\mece-principles.md' -Message 'Historical note must name Barbara Minto, link the primary source, and include the non-affiliation disclaimer.'
        }
        if ($principles -match '30%|25%|15%') {
            Add-ValidationIssue -Issues $issues -Code 'UNSOURCED_PERCENTAGE' -Path 'skills\sgs-mece\references\mece-principles.md' -Message 'Fixed marketing budget percentages are not allowed.'
        }
    }

    $casesPath = Join-Path $resolvedRoot 'tests\sgs-mece\cases.json'
    if (-not (Test-Path -LiteralPath $casesPath -PathType Leaf)) {
        Add-ValidationIssue -Issues $issues -Code 'EVAL_MISSING' -Path 'tests\sgs-mece\cases.json' -Message 'Evaluation cases are required.'
    }
    else {
        try {
            $parsedCases = Get-Utf8Text -Path $casesPath | ConvertFrom-Json
            $cases = @($parsedCases)
            if ($cases.Count -lt 6) {
                Add-ValidationIssue -Issues $issues -Code 'EVAL_COUNT' -Path 'tests\sgs-mece\cases.json' -Message 'At least six evaluation cases are required.'
            }
            $ids = @($cases | ForEach-Object { $_.id })
            if (@($ids | Sort-Object -Unique).Count -ne $ids.Count) {
                Add-ValidationIssue -Issues $issues -Code 'EVAL_DUPLICATE' -Path 'tests\sgs-mece\cases.json' -Message 'Evaluation case ids must be unique.'
            }
            $requiredCategories = @(
                'positive-trigger',
                'specialist-boundary',
                'data-conflict',
                'irreversible-decision',
                'no-fabrication',
                'negative-trigger'
            )
            $caseCategories = @($cases | ForEach-Object { $_.category })
            foreach ($category in $requiredCategories) {
                if ($caseCategories -notcontains $category) {
                    Add-ValidationIssue -Issues $issues -Code 'EVAL_CATEGORY' -Path 'tests\sgs-mece\cases.json' -Message "Missing evaluation category: $category"
                }
            }
        }
        catch {
            Add-ValidationIssue -Issues $issues -Code 'EVAL_JSON' -Path 'tests\sgs-mece\cases.json' -Message "Invalid JSON: $($_.Exception.Message)"
        }
    }

    return $issues
}

function Invoke-ValidatorSelfTest {
    $fixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("sgskills-validator-" + [guid]::NewGuid().ToString('N'))
    try {
        $skillRoot = Join-Path $fixtureRoot 'skills\bad-skill'
        New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'tests\sgs-mece') -Force | Out-Null
        @'
---
name: bad-skill
description: This fixture is intentionally invalid.
type: prompt
---

# 麦肯锡 MECE 原则
'@ | Set-Content -LiteralPath (Join-Path $skillRoot 'SKILL.md') -Encoding UTF8
        '[]' | Set-Content -LiteralPath (Join-Path $fixtureRoot 'tests\sgs-mece\cases.json') -Encoding UTF8

        $issues = @(Invoke-RepoValidation -Root $fixtureRoot)
        $codes = @($issues.Code | Sort-Object -Unique)
        $requiredCodes = @('ROOT_FILE_MISSING', 'FRONTMATTER_KEY', 'BANNED_PHRASE', 'EVAL_COUNT')
        foreach ($requiredCode in $requiredCodes) {
            if ($codes -notcontains $requiredCode) {
                throw "Self-test fixture did not trigger required issue: $requiredCode"
            }
        }

        Write-Output "EXPECTED RED: invalid fixture produced $($issues.Count) issue(s)."
        Write-Output ('EXPECTED CODES: ' + ($codes -join ', '))
        Write-Output 'SELF-TEST PASS'
    }
    finally {
        if (Test-Path -LiteralPath $fixtureRoot) {
            Remove-Item -LiteralPath $fixtureRoot -Recurse -Force
        }
    }
}

if ($SelfTest) {
    Invoke-ValidatorSelfTest
    exit 0
}

$validationIssues = @(Invoke-RepoValidation -Root $RepoRoot)
if ($validationIssues.Count -gt 0) {
    Write-Output "VALIDATION FAILED: $($validationIssues.Count) issue(s)"
    $validationIssues |
        Sort-Object Code, Path |
        Format-Table Code, Path, Message -AutoSize |
        Out-String -Width 240 |
        Write-Output
    exit 1
}

Write-Output 'VALIDATION PASS: repository structure, metadata, references, policy text, and eval fixtures are valid.'
exit 0
