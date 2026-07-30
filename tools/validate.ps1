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

function Add-Issue {
    param(
        [System.Collections.Generic.List[object]]$Issues,
        [string]$Code,
        [string]$Path,
        [string]$Message
    )

    [void]$Issues.Add([PSCustomObject]@{ Code = $Code; Path = $Path; Message = $Message })
}

function Read-Utf8 {
    param([string]$Path)

    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

function Get-Frontmatter {
    param([string]$Path)

    $content = Read-Utf8 -Path $Path
    $match = [regex]::Match(
        $content,
        '\A---\r?\n(?<body>.*?)\r?\n---(?:\r?\n|$)',
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
    if (-not $match.Success) { return $null }

    $fields = [ordered]@{}
    foreach ($line in ($match.Groups['body'].Value -split '\r?\n')) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $field = [regex]::Match($line, '^(?<key>[A-Za-z0-9-]+):\s*(?<value>.*)$')
        if (-not $field.Success) { return $null }
        $fields[$field.Groups['key'].Value] = $field.Groups['value'].Value.Trim().Trim('"').Trim("'")
    }
    return [PSCustomObject]@{ Fields = $fields; Content = $content }
}

function Require-Patterns {
    param(
        [System.Collections.Generic.List[object]]$Issues,
        [string]$Path,
        [string]$Code,
        [string[]]$Patterns
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $content = Read-Utf8 -Path $Path
    foreach ($pattern in $Patterns) {
        if ($content -notmatch $pattern) {
            Add-Issue -Issues $Issues -Code $Code -Path $Path -Message "Missing required pattern: $pattern"
        }
    }
}

function Invoke-RepoValidation {
    param([string]$Root)

    $issues = New-Object 'System.Collections.Generic.List[object]'
    try { $rootPath = (Resolve-Path -LiteralPath $Root).Path }
    catch {
        Add-Issue -Issues $issues -Code 'REPO_MISSING' -Path $Root -Message 'Repository root does not exist.'
        return $issues
    }

    $rootFiles = @(
        'README.md', 'README.en.md', 'LICENSE', 'VERSION', 'CHANGELOG.md', '.gitignore',
        'tools\build.ps1', 'tools\validate.ps1', '.github\workflows\validate.yml'
    )
    foreach ($relative in $rootFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $rootPath $relative) -PathType Leaf)) {
            Add-Issue -Issues $issues -Code 'ROOT_FILE_MISSING' -Path $relative -Message 'Required repository file is missing.'
        }
    }

    $versionPath = Join-Path $rootPath 'VERSION'
    if ((Test-Path -LiteralPath $versionPath) -and (Read-Utf8 -Path $versionPath).Trim() -ne '2.0.0') {
        Add-Issue -Issues $issues -Code 'VERSION_INVALID' -Path 'VERSION' -Message 'Version must be 2.0.0.'
    }

    $legacySkillName = 'sg' + 's-mece'
    foreach ($readme in @('README.md', 'README.en.md')) {
        Require-Patterns -Issues $issues -Path (Join-Path $rootPath $readme) -Code 'README_CONTENT' -Patterns @(
            'Source Available', 'Not Open Source', '\$sg-mece', '\$sg-ceo-vision',
            'sg-mece-2\.0\.0\.zip', 'sg-ceo-vision-2\.0\.0\.zip', $legacySkillName,
            'github\.com/sgskills/ecommerce-skills/tree/main/skills/sg-mece',
            'github\.com/sgskills/ecommerce-skills/tree/main/skills/sg-ceo-vision',
            'skills/', 'github\.com/sgskills', 'v\.douyin\.com/O8hIsRzfjqQ', 'Built by  \[@xstevenzhang\]'
        )
    }
    Require-Patterns -Issues $issues -Path (Join-Path $rootPath 'LICENSE') -Code 'LICENSE_CONTENT' -Patterns @(
        'SGSkills Internal Use License 1\.0', 'Source Available', 'Not Open Source', 'sg-mece', 'sg-ceo-vision',
        '\u4e2a\u4eba\u5b66\u4e60', '\u81ea\u8eab\u7535\u5546\u7ecf\u8425', '\u5185\u90e8\u4fee\u6539',
        '\u516c\u5f00\u518d\u5206\u53d1', '\u8f6c\u552e', '\u767d\u6807', '\u4ed8\u8d39\u8bfe\u7a0b', '\u4e0d\u6784\u6210\u6cd5\u5f8b\u610f\u89c1'
    )
    Require-Patterns -Issues $issues -Path (Join-Path $rootPath '.gitignore') -Code 'GITIGNORE_CONTENT' -Patterns @(
        '(?m)^/dist/\r?$', '(?m)^/\.work/\r?$'
    )
    Require-Patterns -Issues $issues -Path (Join-Path $rootPath 'CHANGELOG.md') -Code 'CHANGELOG_CONTENT' -Patterns @(
        'v2\.0\.0', $legacySkillName, 'sg-mece', 'sg-ceo-vision'
    )

    $ceoVisionDisplayName = [regex]::Unescape('CEO Vision\uFF5CCEO\u89c6\u89d2')
    $skillSpecs = [ordered]@{
        'sg-mece' = @{
            displayName = 'sg-mece'
            references = @('frameworks.md', 'mece-principles.md', 'questions.md')
            assets = @()
            categories = @('positive-trigger', 'specialist-boundary', 'data-conflict', 'irreversible-decision', 'no-fabrication', 'negative-trigger')
        }
        'sg-ceo-vision' = @{
            displayName = $ceoVisionDisplayName
            references = @('evidence-and-opportunity-rubric.md', 'report-content-schema.md')
            assets = @('ceo-vision-report-template.html')
            categories = @(
                'positive-trigger', 'negative-trigger', 'insufficient-evidence', 'irreversible-decision',
                'independence-boundary', 'html-output-contract', 'intellectual-property-risk',
                'intellectual-property-asset', 'intellectual-property-non-trigger'
            )
        }
    }

    $skillsPath = Join-Path $rootPath 'skills'
    if (-not (Test-Path -LiteralPath $skillsPath -PathType Container)) {
        Add-Issue -Issues $issues -Code 'SKILLS_ROOT_MISSING' -Path 'skills' -Message 'skills directory is missing.'
    }
    else {
        $actualNames = @(Get-ChildItem -LiteralPath $skillsPath -Directory | ForEach-Object { $_.Name } | Sort-Object)
        $expectedNames = @($skillSpecs.Keys | Sort-Object)
        if (($actualNames -join '|') -ne ($expectedNames -join '|')) {
            Add-Issue -Issues $issues -Code 'SKILL_SET' -Path 'skills' -Message "Expected exactly: $($expectedNames -join ', '). Found: $($actualNames -join ', ')."
        }

        foreach ($skillName in $expectedNames) {
            $spec = $skillSpecs[$skillName]
            $skillPath = Join-Path $skillsPath $skillName
            $relative = "skills\\$skillName"
            $skillFile = Join-Path $skillPath 'SKILL.md'
            if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
                Add-Issue -Issues $issues -Code 'SKILL_FILE_MISSING' -Path $relative -Message 'SKILL.md is required.'
                continue
            }

            foreach ($item in (Get-ChildItem -LiteralPath $skillPath -Force)) {
                if (@('SKILL.md', 'agents', 'references', 'assets', 'scripts') -notcontains $item.Name) {
                    Add-Issue -Issues $issues -Code 'RUNTIME_ITEM_UNEXPECTED' -Path "$relative\\$($item.Name)" -Message 'Unexpected runtime item.'
                }
            }
            foreach ($docName in @('README.md', 'QUICKREF.md', 'CHANGELOG.md')) {
                if (Test-Path -LiteralPath (Join-Path $skillPath $docName)) {
                    Add-Issue -Issues $issues -Code 'RUNTIME_DOC_PRESENT' -Path "$relative\\$docName" -Message 'Repository documentation is not allowed in a runtime skill.'
                }
            }
            if (Test-Path -LiteralPath (Join-Path $skillPath 'KNOWLEDGE')) {
                Add-Issue -Issues $issues -Code 'LEGACY_DIRECTORY' -Path "$relative\\KNOWLEDGE" -Message 'Use the standard references directory.'
            }

            $frontmatter = Get-Frontmatter -Path $skillFile
            if ($null -eq $frontmatter) {
                Add-Issue -Issues $issues -Code 'FRONTMATTER_INVALID' -Path "$relative\\SKILL.md" -Message 'Frontmatter is invalid.'
                continue
            }
            foreach ($key in $frontmatter.Fields.Keys) {
                if (@('name', 'description', 'license') -notcontains $key) {
                    Add-Issue -Issues $issues -Code 'FRONTMATTER_KEY' -Path "$relative\\SKILL.md" -Message "Unexpected frontmatter key: $key"
                }
            }
            foreach ($key in @('name', 'description', 'license')) {
                if (-not $frontmatter.Fields.Contains($key) -or [string]::IsNullOrWhiteSpace($frontmatter.Fields[$key])) {
                    Add-Issue -Issues $issues -Code 'FRONTMATTER_REQUIRED' -Path "$relative\\SKILL.md" -Message "Missing frontmatter key: $key"
                }
            }
            if ($frontmatter.Fields['name'] -ne $skillName) {
                Add-Issue -Issues $issues -Code 'SKILL_NAME' -Path "$relative\\SKILL.md" -Message 'name must equal its directory.'
            }
            if ($frontmatter.Fields['description'].Length -gt 1024 -or $frontmatter.Fields['description'] -notmatch '^Use when ') {
                Add-Issue -Issues $issues -Code 'DESCRIPTION_FORMAT' -Path "$relative\\SKILL.md" -Message 'description must start with Use when and be under 1024 characters.'
            }
            if ($frontmatter.Fields['description'] -notmatch '\u7535\u5546' -or
                $frontmatter.Fields['description'] -notmatch '\u8fb9\u754c\u4e0d\u6e05|\u8de8\u6a21\u5757|\u6a21\u7cca' -or
                $frontmatter.Fields['description'] -notmatch '\u4e0d\u9002\u7528|\u5df2\u6709\u660e\u786e|\u4e0d\u8981') {
                Add-Issue -Issues $issues -Code 'DESCRIPTION_BOUNDARY' -Path "$relative\\SKILL.md" -Message 'description must include ecommerce triggers, ambiguous/cross-module scope, and an anti-trigger.'
            }

            if ($skillName -eq 'sg-ceo-vision') {
                Require-Patterns -Issues $issues -Path $skillFile -Code 'CEO_VISION_CONTRACT' -Patterns @(
                    ('(?m)^#\s+' + [regex]::Escape($ceoVisionDisplayName) + '\s*$'),
                    '(?m)^#{1,6}\s+.*STOP\s*/\s*CHECKPOINT.*$',
                    '(?m)^#{1,6}\s+.*\u5931\u8d25\u6062\u590d\u8868.*$',
                    '\u7ed3\u8bba\uFF5C\u8bc1\u636e\u72b6\u6001\uFF5C\u6765\u6e90\u4f4d\u7f6e\uFF5C\u4f1a\u6539\u53d8\u7ed3\u8bba\u7684\u6761\u4ef6',
                    '(?m)^#{1,6}\s+.*\u7981\u6b62\u8bef\u5224\u6e05\u5355.*$'
                )
                Require-Patterns -Issues $issues -Path $skillFile -Code 'CEO_VISION_IP_CONTRACT' -Patterns @(
                    '\u77e5\u8bc6\u4ea7\u6743\u4e0e\u54c1\u724c\u8d44\u4ea7',
                    '\u6743\u5c5e\u6216\u6388\u6743\u8bc1\u636e',
                    '\u5c40\u90e8\s*STOP'
                )

                $opportunityRubricPath = Join-Path $skillPath 'references\evidence-and-opportunity-rubric.md'
                Require-Patterns -Issues $issues -Path $opportunityRubricPath -Code 'CEO_VISION_IP_CONTRACT' -Patterns @(
                    '(?m)^#{1,6}\s+.*\u77e5\u8bc6\u4ea7\u6743\u4e0e\u54c1\u724c\u8d44\u4ea7\u68c0\u67e5\u70b9.*$',
                    '\u8d44\u4ea7\uFF5C\u6743\u5229\u4eba\uFF5C\u6743\u5c5e\u6216\u6388\u6743\u8bc1\u636e\uFF5C\u4f7f\u7528\u8303\u56f4\uFF5C\u4e3b\u8981\u98ce\u9669\uFF5C\u4e0b\u4e00\u6b65',
                    '\u65e0\u76f8\u5173\u4fe1\u53f7\u65f6\u4e0d\u589e\u52a0\u62a5\u544a\u8d1f\u62c5',
                    '\u4e0d\u628a\u53e3\u5934\u4fdd\u8bc1\u5f53\u4f5c\u6743\u5c5e\u6216\u6388\u6743\u8bc1\u636e',
                    '\u4e0d\u628a\u6a21\u578b\u5224\u65ad\u5f53\u4f5c\u6cd5\u5f8b\u7ed3\u8bba'
                )

                $reportSchemaPath = Join-Path $skillPath 'references\report-content-schema.md'
                Require-Patterns -Issues $issues -Path $reportSchemaPath -Code 'CEO_VISION_IP_REPORT' -Patterns @(
                    '\u77e5\u8bc6\u4ea7\u6743\u4e0e\u54c1\u724c\u8d44\u4ea7',
                    '\u53ea\u5728\u89e6\u53d1\u68c0\u67e5\u70b9\u65f6\u5c55\u793a'
                )
            }

            foreach ($reference in $spec.references) {
                if (-not (Test-Path -LiteralPath (Join-Path $skillPath "references\\$reference") -PathType Leaf)) {
                    Add-Issue -Issues $issues -Code 'REFERENCE_REQUIRED' -Path "$relative\\references\\$reference" -Message 'Required reference is missing.'
                }
            }
            foreach ($asset in @($spec.assets)) {
                if (-not (Test-Path -LiteralPath (Join-Path $skillPath "assets\\$asset") -PathType Leaf)) {
                    Add-Issue -Issues $issues -Code 'ASSET_REQUIRED' -Path "$relative\\assets\\$asset" -Message 'Required asset is missing.'
                }
            }
            $assetPath = Join-Path $skillPath 'assets\\ceo-vision-report-template.html'
            if ($skillName -eq 'sg-ceo-vision' -and (Test-Path -LiteralPath $assetPath)) {
                Require-Patterns -Issues $issues -Path $assetPath -Code 'HTML_TEMPLATE_CONTENT' -Patterns @(
                    '<!DOCTYPE html>', 'CEO VISION', 'DESIGNED BY SHIGUANG', '\u77e5\u8bc6\u4ea7\u6743\u4e0e\u54c1\u724c\u8d44\u4ea7'
                )
            }

            $referencedPaths = [regex]::Matches($frontmatter.Content, '(?:references|scripts|assets)/[A-Za-z0-9._/-]+') | ForEach-Object { $_.Value } | Sort-Object -Unique
            foreach ($referencedPath in $referencedPaths) {
                $platformPath = $referencedPath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
                if (-not (Test-Path -LiteralPath (Join-Path $skillPath $platformPath) -PathType Leaf)) {
                    Add-Issue -Issues $issues -Code 'REFERENCE_MISSING' -Path "$relative\\SKILL.md" -Message "Referenced file does not exist: $referencedPath"
                }
            }

            $openaiPath = Join-Path $skillPath 'agents\\openai.yaml'
            if (-not (Test-Path -LiteralPath $openaiPath -PathType Leaf)) {
                Add-Issue -Issues $issues -Code 'OPENAI_YAML_MISSING' -Path "$relative\\agents\\openai.yaml" -Message 'Codex interface metadata is required.'
            }
            else {
                Require-Patterns -Issues $issues -Path $openaiPath -Code 'OPENAI_YAML_CONTENT' -Patterns @(
                    ('display_name:\s*.*' + [regex]::Escape($spec.displayName)), 'short_description:',
                    [regex]::Escape(('$' + $skillName)), 'allow_implicit_invocation:\s*true'
                )
            }

            $casesPath = Join-Path $rootPath "tests\\$skillName\\cases.json"
            if (-not (Test-Path -LiteralPath $casesPath -PathType Leaf)) {
                Add-Issue -Issues $issues -Code 'EVAL_MISSING' -Path "tests\\$skillName\\cases.json" -Message 'Evaluation cases are required.'
            }
            else {
                try {
                    $cases = ConvertFrom-Json -InputObject (Read-Utf8 -Path $casesPath)
                    if ($cases.Count -lt 6) { Add-Issue -Issues $issues -Code 'EVAL_COUNT' -Path "tests\\$skillName\\cases.json" -Message 'At least six cases are required.' }
                    $ids = @($cases | ForEach-Object { $_.id })
                    if (@($ids | Sort-Object -Unique).Count -ne $ids.Count) { Add-Issue -Issues $issues -Code 'EVAL_DUPLICATE' -Path "tests\\$skillName\\cases.json" -Message 'Case ids must be unique.' }
                    $categories = @($cases | ForEach-Object { $_.category })
                    foreach ($category in $spec.categories) {
                        if ($categories -notcontains $category) { Add-Issue -Issues $issues -Code 'EVAL_CATEGORY' -Path "tests\\$skillName\\cases.json" -Message "Missing category: $category" }
                    }
                }
                catch { Add-Issue -Issues $issues -Code 'EVAL_JSON' -Path "tests\\$skillName\\cases.json" -Message $_.Exception.Message }
            }
        }
    }

    $principlesPath = Join-Path $rootPath 'skills\\sg-mece\\references\\mece-principles.md'
    if (Test-Path -LiteralPath $principlesPath) {
        $principles = Read-Utf8 -Path $principlesPath
        if ($principles -notmatch 'Barbara Minto' -or
            $principles -notmatch 'https://www\.mckinsey\.com/alumni/news-and-events/global-news/alumni-news/barbara-minto-mece-i-invented-it-so-i-get-to-say-how-to-pronounce-it' -or
            $principles -notmatch '\u65e0\u96b6\u5c5e.*\u5408\u4f5c.*\u80cc\u4e66') {
            Add-Issue -Issues $issues -Code 'SOURCE_NOTE' -Path 'skills\\sg-mece\\references\\mece-principles.md' -Message 'Historical note must name Barbara Minto, link the primary source, and include the non-affiliation disclaimer.'
        }
        if ($principles -match '30%|25%|15%') {
            Add-Issue -Issues $issues -Code 'UNSOURCED_PERCENTAGE' -Path 'skills\\sg-mece\\references\\mece-principles.md' -Message 'Fixed budget percentages are not allowed.'
        }
    }

    $legacyPrefix = 'sg' + 's-'
    $allowedLegacyFiles = @('README.md', 'README.en.md', 'CHANGELOG.md')
    $scanFiles = Get-ChildItem -LiteralPath $rootPath -Recurse -File | Where-Object {
        $_.FullName -notmatch '\\.git\\|\\.work\\|\\dist\\' -and $_.Extension -in @('.md', '.yaml', '.yml', '.json', '.ps1', '.html', '.txt')
    }
    foreach ($file in $scanFiles) {
        $relative = $file.FullName.Substring($rootPath.Length).TrimStart('\\')
        if ($relative.Contains($legacyPrefix)) {
            Add-Issue -Issues $issues -Code 'LEGACY_PREFIX' -Path $relative -Message 'Legacy prefix remains in a path.'
        }
        $content = Read-Utf8 -Path $file.FullName
        foreach ($banned in @(
            [regex]::Unescape('\u9ea6\u80af\u9521 MECE \u539f\u5219'),
            [regex]::Unescape('\u7406\u8bba\u539f\u5178'),
            [regex]::Unescape('\u6bcf\u4e2a\u6846\u67b6\u5747\u6ee1\u8db3 MECE'),
            [regex]::Unescape('5\u95ee'),
            [regex]::Unescape('\u2b50\u2b50'),
            [regex]::Unescape('CEO \u7684\u773c\u5149'),
            [regex]::Unescape('CEO\u7684\u773c\u5149')
        )) {
            if ($content.Contains($banned)) {
                Add-Issue -Issues $issues -Code 'BANNED_PHRASE' -Path $relative -Message "Banned or unsupported phrase found: $banned"
            }
        }
        if ($content -match '\u9ea6\u80af\u9521|McKinsey') {
            $allowedSource = $relative -eq (Join-Path (Join-Path (Join-Path 'skills' 'sg-mece') 'references') 'mece-principles.md') -or
                $relative -eq (Join-Path 'tools' 'validate.ps1')
            if (-not $allowedSource) {
                Add-Issue -Issues $issues -Code 'MCKINSEY_SCOPE' -Path $relative -Message 'McKinsey may appear only in the historical source note.'
            }
        }
        if ($content.Contains($legacyPrefix) -and $allowedLegacyFiles -notcontains $relative) {
            Add-Issue -Issues $issues -Code 'LEGACY_PREFIX' -Path $relative -Message 'Legacy prefix is allowed only in migration notes.'
        }
    }
    return $issues
}

function Invoke-ValidatorSelfTest {
    param([string]$SourceRoot)

    $sourceIssues = @(Invoke-RepoValidation -Root $SourceRoot)
    if ($sourceIssues.Count -gt 0) { throw ('Self-test requires a valid repository. Got: ' + (($sourceIssues.Code | Sort-Object -Unique) -join ', ')) }

    $fixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('sgskills-validator-' + [guid]::NewGuid().ToString('N'))
    $legacyPrefix = 'sg' + 's-'
    try {
        New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
        foreach ($file in @('README.md', 'README.en.md', 'LICENSE', 'VERSION', 'CHANGELOG.md', '.gitignore')) { Copy-Item -LiteralPath (Join-Path $SourceRoot $file) -Destination $fixtureRoot }
        foreach ($directory in @('.github', 'skills', 'tests', 'tools')) { Copy-Item -LiteralPath (Join-Path $SourceRoot $directory) -Destination $fixtureRoot -Recurse }
        $fixtureSkillPath = Join-Path $fixtureRoot 'skills\\sg-ceo-vision\\SKILL.md'
        $fixtureOpportunityRubricPath = Join-Path $fixtureRoot 'skills\\sg-ceo-vision\\references\\evidence-and-opportunity-rubric.md'
        $fixtureReportSchemaPath = Join-Path $fixtureRoot 'skills\\sg-ceo-vision\\references\\report-content-schema.md'
        $failureRecoveryHeading = [regex]::Unescape('## \u5931\u8d25\u6062\u590d\u8868')
        $evidenceLedgerFields = [regex]::Unescape('\u7ed3\u8bba\uFF5C\u8bc1\u636e\u72b6\u6001\uFF5C\u6765\u6e90\u4f4d\u7f6e\uFF5C\u4f1a\u6539\u53d8\u7ed3\u8bba\u7684\u6761\u4ef6')
        $misjudgmentHeading = [regex]::Unescape('## \u7981\u6b62\u8bef\u5224\u6e05\u5355')
        $ipCheckpointHeading = [regex]::Unescape('## \u77e5\u8bc6\u4ea7\u6743\u4e0e\u54c1\u724c\u8d44\u4ea7\u68c0\u67e5\u70b9')
        $ipLedgerFields = [regex]::Unescape('\u8d44\u4ea7\uFF5C\u6743\u5229\u4eba\uFF5C\u6743\u5c5e\u6216\u6388\u6743\u8bc1\u636e\uFF5C\u4f7f\u7528\u8303\u56f4\uFF5C\u4e3b\u8981\u98ce\u9669\uFF5C\u4e0b\u4e00\u6b65')
        $ipReportSection = [regex]::Unescape('**\u77e5\u8bc6\u4ea7\u6743\u4e0e\u54c1\u724c\u8d44\u4ea7**')
        $legacyDirectory = Join-Path $fixtureRoot ("skills\\$legacyPrefix" + 'fixture')
        New-Item -ItemType Directory -Path $legacyDirectory -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $legacyDirectory 'SKILL.md') -Force | Out-Null
        $redIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
        if (@($redIssues.Code) -notcontains 'LEGACY_PREFIX') { throw ('Legacy fixture did not trigger LEGACY_PREFIX. Got: ' + (($redIssues | ForEach-Object { $_.Code }) -join ', ')) }
        Write-Output "EXPECTED RED: legacy-prefix fixture produced $($redIssues.Count) issue(s)."
        Remove-Item -LiteralPath $legacyDirectory -Recurse -Force
        $greenIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
        if ($greenIssues.Count -gt 0) { throw ('Fixture did not recover: ' + (($greenIssues.Code | Sort-Object -Unique) -join ', ')) }
        Write-Output 'LEGACY_PREFIX_RED_GREEN PASS'

        # Each control is independently removed and restored below.
        $validContract = Read-Utf8 -Path $fixtureSkillPath
        $stopCheckpointHeading = [regex]::Match($validContract, '(?m)^#{1,6}\s+.*STOP\s*/\s*CHECKPOINT.*$').Value
        $contractControls = @(
            [PSCustomObject]@{ Name = 'STOP/CHECKPOINT'; Text = $stopCheckpointHeading },
            [PSCustomObject]@{ Name = 'failure-recovery'; Text = $failureRecoveryHeading },
            [PSCustomObject]@{ Name = 'evidence-ledger'; Text = $evidenceLedgerFields },
            [PSCustomObject]@{ Name = 'misjudgment-list'; Text = $misjudgmentHeading }
        )
        foreach ($control in $contractControls) {
            if ([string]::IsNullOrWhiteSpace($control.Text) -or -not $validContract.Contains($control.Text)) {
                throw "CEO Vision control fixture is missing expected control: $($control.Name)"
            }
            $missingControl = $validContract.Replace($control.Text, '')
            if ($missingControl -eq $validContract) {
                throw "CEO Vision control fixture did not remove control: $($control.Name)"
            }
            [System.IO.File]::WriteAllText($fixtureSkillPath, $missingControl, [System.Text.Encoding]::UTF8)
            $contractRedIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
            $contractRedCodes = @($contractRedIssues | ForEach-Object { $_.Code })
            if ($contractRedCodes -notcontains 'CEO_VISION_CONTRACT') {
                throw ('CEO Vision control fixture did not trigger CEO_VISION_CONTRACT. Got: ' + ($contractRedCodes -join ', '))
            }
            Write-Output "EXPECTED RED: CEO Vision $($control.Name) fixture produced $($contractRedIssues.Count) issue(s)."
            [System.IO.File]::WriteAllText($fixtureSkillPath, $validContract, [System.Text.Encoding]::UTF8)
            $contractGreenIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
            if ($contractGreenIssues.Count -gt 0) { throw ('CEO Vision control fixture did not recover: ' + (($contractGreenIssues.Code | Sort-Object -Unique) -join ', ')) }
        }

        Write-Output 'CEO_VISION_CONTRACT_RED_GREEN PASS'

        $ipControls = @(
            [PSCustomObject]@{
                Name = 'checkpoint-heading'
                Path = $fixtureOpportunityRubricPath
                Code = 'CEO_VISION_IP_CONTRACT'
                Text = $ipCheckpointHeading
            },
            [PSCustomObject]@{
                Name = 'ledger-fields'
                Path = $fixtureOpportunityRubricPath
                Code = 'CEO_VISION_IP_CONTRACT'
                Text = $ipLedgerFields
            },
            [PSCustomObject]@{
                Name = 'report-section'
                Path = $fixtureReportSchemaPath
                Code = 'CEO_VISION_IP_REPORT'
                Text = $ipReportSection
            }
        )
        foreach ($control in $ipControls) {
            $validIpContract = Read-Utf8 -Path $control.Path
            if ([string]::IsNullOrWhiteSpace($control.Text) -or -not $validIpContract.Contains($control.Text)) {
                throw "CEO Vision IP fixture is missing expected control: $($control.Name)"
            }
            $missingIpControl = $validIpContract.Replace($control.Text, '')
            [System.IO.File]::WriteAllText($control.Path, $missingIpControl, [System.Text.Encoding]::UTF8)
            $ipRedIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
            $ipRedCodes = @($ipRedIssues | ForEach-Object { $_.Code })
            if ($ipRedCodes -notcontains $control.Code) {
                throw ('CEO Vision IP fixture did not trigger ' + $control.Code + '. Got: ' + ($ipRedCodes -join ', '))
            }
            Write-Output "EXPECTED RED: CEO Vision IP $($control.Name) fixture produced $($ipRedIssues.Count) issue(s)."
            [System.IO.File]::WriteAllText($control.Path, $validIpContract, [System.Text.Encoding]::UTF8)
            $ipGreenIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
            if ($ipGreenIssues.Count -gt 0) {
                throw ('CEO Vision IP fixture did not recover: ' + (($ipGreenIssues.Code | Sort-Object -Unique) -join ', '))
            }
        }

        Write-Output 'CEO_VISION_IP_RED_GREEN PASS'
        Write-Output 'SELF-TEST PASS'
    }
    finally {
        if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
}

if ($SelfTest) {
    Invoke-ValidatorSelfTest -SourceRoot $RepoRoot
    exit 0
}

$validationIssues = @(Invoke-RepoValidation -Root $RepoRoot)
if ($validationIssues.Count -gt 0) {
    Write-Output "VALIDATION FAILED: $($validationIssues.Count) issue(s)"
    $validationIssues | Sort-Object Code, Path | ForEach-Object { Write-Output ("[{0}] {1} :: {2}" -f $_.Code, $_.Path, $_.Message) }
    exit 1
}
Write-Output 'VALIDATION PASS'
