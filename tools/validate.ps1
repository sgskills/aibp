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

    [void]$Issues.Add(
        [PSCustomObject]@{
            Code = $Code
            Path = $Path
            Message = $Message
        }
    )
}

function Read-Utf8 {
    param([string]$Path)

    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

function Write-Utf8 {
    param(
        [string]$Path,
        [string]$Content
    )

    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

function Normalize-LineEndings {
    param([string]$Content)

    return $Content.Replace("`r`n", "`n")
}

function Get-UpdateContract {
    param(
        [string]$Root,
        [System.Collections.Generic.List[object]]$Issues
    )

    $templates = @{}
    foreach ($fileName in @('check-update.ps1', 'check-update.sh', 'skill-entry.md')) {
        $relative = "tools\update-check\$fileName"
        $path = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            Add-Issue -Issues $Issues -Code 'UPDATE_TEMPLATE_MISSING' -Path $relative -Message 'The canonical update-check template is required.'
            continue
        }
        $content = Normalize-LineEndings -Content (Read-Utf8 -Path $path)
        if ([string]::IsNullOrWhiteSpace($content)) {
            Add-Issue -Issues $Issues -Code 'UPDATE_TEMPLATE_INVALID' -Path $relative -Message 'The canonical update-check template must not be empty.'
            continue
        }
        $templates[$fileName] = $content
        if ($fileName -ne 'skill-entry.md') {
            $templates["$fileName.bytes"] = [System.Convert]::ToBase64String([System.IO.File]::ReadAllBytes($path))
        }
    }

    $start = '<!-- AIBP-UPDATE-CHECK:START -->'
    $end = '<!-- AIBP-UPDATE-CHECK:END -->'
    $entryPattern = [regex]::Escape($start) + '[\s\S]*?' + [regex]::Escape($end)
    if ($templates.ContainsKey('skill-entry.md')) {
        $entry = $templates['skill-entry.md'].Trim()
        if (
            [regex]::Matches($entry, [regex]::Escape($start)).Count -ne 1 -or
            [regex]::Matches($entry, [regex]::Escape($end)).Count -ne 1 -or
            $entry -cnotmatch ('\A' + $entryPattern + '\z') -or
            -not $entry.Contains('scripts/check-update.ps1') -or
            -not $entry.Contains('scripts/check-update.sh')
        ) {
            Add-Issue -Issues $Issues -Code 'UPDATE_TEMPLATE_INVALID' -Path 'tools\update-check\skill-entry.md' -Message 'The entry template must be one complete managed block wired to both runtime scripts.'
            $templates.Remove('skill-entry.md')
        }
        else {
            $templates['skill-entry.md'] = $entry
        }
    }

    return [PSCustomObject]@{
        Templates = $templates
        Start = $start
        End = $end
        EntryPattern = $entryPattern
    }
}

function Test-SkillUpdateContract {
    param(
        [System.Collections.Generic.List[object]]$Issues,
        [string]$SkillPath,
        [string]$RelativeSkill,
        [string]$Version,
        [object]$Contract
    )

    foreach ($fileName in @('check-update.ps1', 'check-update.sh', 'update-version.txt')) {
        $relative = "$RelativeSkill\scripts\$fileName"
        $path = Join-Path $SkillPath "scripts\$fileName"
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            Add-Issue -Issues $Issues -Code 'UPDATE_FILE_MISSING' -Path $relative -Message 'Every discovered Skill requires its own update-check runtime files; run the explicit sync tool before validating.'
            continue
        }
        if ($fileName -eq 'update-version.txt') {
            $expectedBytes = [System.Text.Encoding]::UTF8.GetBytes($Version + "`n")
            $actualBytes = [System.IO.File]::ReadAllBytes($path)
            if ([System.Convert]::ToBase64String($actualBytes) -cne [System.Convert]::ToBase64String($expectedBytes)) {
                Add-Issue -Issues $Issues -Code 'UPDATE_VERSION_MISMATCH' -Path $relative -Message 'Packaged update version must equal VERSION followed by one newline.'
            }
        }
        elseif ($Contract.Templates.ContainsKey("$fileName.bytes") -and [System.Convert]::ToBase64String([System.IO.File]::ReadAllBytes($path)) -cne $Contract.Templates["$fileName.bytes"]) {
            Add-Issue -Issues $Issues -Code 'UPDATE_TEMPLATE_DRIFT' -Path $relative -Message 'Packaged runtime differs from the canonical template; validation never repairs it automatically.'
        }
    }

    $skillContent = Normalize-LineEndings -Content (Read-Utf8 -Path (Join-Path $SkillPath 'SKILL.md'))
    $starts = [regex]::Matches($skillContent, [regex]::Escape($Contract.Start)).Count
    $ends = [regex]::Matches($skillContent, [regex]::Escape($Contract.End)).Count
    if ($starts -eq 0 -and $ends -eq 0) {
        Add-Issue -Issues $Issues -Code 'UPDATE_ENTRY_MISSING' -Path "$RelativeSkill\SKILL.md" -Message 'The managed update-check entry block is required.'
        return
    }
    if ($starts -ne 1 -or $ends -ne 1) {
        Add-Issue -Issues $Issues -Code 'UPDATE_ENTRY_INVALID' -Path "$RelativeSkill\SKILL.md" -Message 'The entry must have exactly one start marker and one end marker.'
        return
    }
    $entryMatch = [regex]::Match($skillContent, $Contract.EntryPattern)
    if (-not $entryMatch.Success) {
        Add-Issue -Issues $Issues -Code 'UPDATE_ENTRY_INVALID' -Path "$RelativeSkill\SKILL.md" -Message 'The managed entry markers are out of order.'
    }
    elseif ($Contract.Templates.ContainsKey('skill-entry.md') -and $entryMatch.Value -cne $Contract.Templates['skill-entry.md']) {
        Add-Issue -Issues $Issues -Code 'UPDATE_ENTRY_DRIFT' -Path "$RelativeSkill\SKILL.md" -Message 'The complete entry block must equal the canonical entry template.'
    }
    elseif ($entryMatch.Success) {
        $fenceCharacter = ''
        $fenceLength = 0
        foreach ($line in ($skillContent.Substring(0, $entryMatch.Index) -split "`n")) {
            if ($fenceCharacter) {
                $closingPattern = '^[ \t]{0,3}' + [regex]::Escape($fenceCharacter) + '{' + $fenceLength + ',}[ \t]*$'
                if ($line -match $closingPattern) { $fenceCharacter = '' }
            }
            else {
                $fenceMatch = [regex]::Match($line, '^[ \t]{0,3}(?<fence>`{3,}|~{3,})')
                if ($fenceMatch.Success) {
                    $fenceCharacter = $fenceMatch.Groups['fence'].Value.Substring(0, 1)
                    $fenceLength = $fenceMatch.Groups['fence'].Value.Length
                }
            }
        }
        if ($fenceCharacter) {
            Add-Issue -Issues $Issues -Code 'UPDATE_ENTRY_IN_FENCE' -Path "$RelativeSkill\SKILL.md" -Message 'The executable managed entry must not be hidden inside a fenced Markdown example.'
        }
    }
}

function Get-Frontmatter {
    param([string]$Path)

    $content = Read-Utf8 -Path $Path
    $match = [regex]::Match(
        $content,
        '\A---\r?\n(?<body>.*?)\r?\n---(?:\r?\n|$)',
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
    if (-not $match.Success) {
        return $null
    }

    $lines = @($match.Groups['body'].Value -split '\r?\n')
    $fields = [ordered]@{}
    for ($index = 0; $index -lt $lines.Count; $index++) {
        $line = $lines[$index]
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $fieldMatch = [regex]::Match(
            $line,
            '^(?<key>[A-Za-z0-9-]+):\s*(?<value>.*)$'
        )
        if (-not $fieldMatch.Success) {
            return $null
        }

        $key = $fieldMatch.Groups['key'].Value
        $rawValue = $fieldMatch.Groups['value'].Value.Trim()
        if ($fields.Contains($key)) {
            return $null
        }

        if ($rawValue -in @('|', '>')) {
            $scalarLines = New-Object 'System.Collections.Generic.List[string]'
            $index++
            while ($index -lt $lines.Count) {
                $scalarLine = $lines[$index]
                if ([string]::IsNullOrWhiteSpace($scalarLine)) {
                    [void]$scalarLines.Add('')
                    $index++
                    continue
                }
                if ($scalarLine -notmatch '^\s+') {
                    $index--
                    break
                }
                [void]$scalarLines.Add($scalarLine.Trim())
                $index++
            }
            if ($rawValue -eq '>') {
                $value = ($scalarLines -join ' ').Trim()
            }
            else {
                $value = ($scalarLines -join "`n").Trim()
            }
        }
        else {
            if (
                $rawValue -match '^\[[^\]]*$' -or
                $rawValue -match '^"[^"]*$' -or
                $rawValue -match "^'[^']*$"
            ) {
                return $null
            }
            $value = $rawValue.Trim('"').Trim("'")
        }
        $fields[$key] = $value
    }

    return [PSCustomObject]@{
        Fields = $fields
        Content = $content
    }
}

function Require-Pattern {
    param(
        [System.Collections.Generic.List[object]]$Issues,
        [string]$Path,
        [string]$Code,
        [string]$Pattern,
        [string]$Message
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    if ((Read-Utf8 -Path $Path) -notmatch $Pattern) {
        Add-Issue -Issues $Issues -Code $Code -Path $Path -Message $Message
    }
}

function Test-DescriptionNarrative {
    param(
        [System.Collections.Generic.List[object]]$Issues,
        [string]$RelativePath,
        [string]$Description
    )

    $normalized = ($Description -replace '\s+', ' ').Trim()
    if ($normalized.Length -gt 2048) {
        Add-Issue -Issues $Issues -Code 'DESCRIPTION_LENGTH' -Path $RelativePath -Message 'description must be at most 2048 characters.'
    }
    $firstMatch = [regex]::Match($normalized, '^.*?[\u3002.!?\uFF01\uFF1F](?:\s|$)')
    if ($firstMatch.Success) {
        $firstSentence = $firstMatch.Value.Trim()
        $remainder = $normalized.Substring($firstMatch.Length).Trim()
    }
    else {
        $firstSentence = $normalized
        $remainder = ''
    }

    if (
        $firstSentence.Length -lt 10 -or
        $firstSentence -match '^(Use when|Trigger|\u89e6\u53d1|\u89e6\u53d1\u65b9\u5f0f|\u5f53\u7528\u6237|\u7528\u6237\u9700\u8981|\u9002\u7528\u4e8e)'
    ) {
        Add-Issue -Issues $Issues -Code 'DESC_FUNCTION_FIRST' -Path $RelativePath -Message 'description must start with a standalone functional definition, not trigger wording.'
    }
    if ($remainder -notmatch '(\u89e6\u53d1\u65b9\u5f0f|\u9002\u7528|\u7528\u6237|Use when|Trigger)') {
        Add-Issue -Issues $Issues -Code 'DESC_TRIGGER_AFTER' -Path $RelativePath -Message 'trigger information must follow the functional first sentence.'
    }
    if ($normalized -notmatch '(\u4e0d\u7528\u4e8e|\u4e0d\u9002\u7528|\u8ba9\u4f4d|Not for|not for)') {
        Add-Issue -Issues $Issues -Code 'DESC_ANTI_TRIGGER' -Path $RelativePath -Message 'description must include an anti-trigger or handoff boundary.'
    }
}

function Invoke-RepoValidation {
    param([string]$Root)

    $issues = New-Object 'System.Collections.Generic.List[object]'
    try {
        $rootPath = (Resolve-Path -LiteralPath $Root).Path
    }
    catch {
        Add-Issue -Issues $issues -Code 'REPO_MISSING' -Path $Root -Message 'Repository root does not exist.'
        return $issues
    }

    $requiredRootFiles = @(
        'README.md',
        'README.en.md',
        'AGENTS.md',
        'LICENSE',
        'VERSION',
        'CHANGELOG.md',
        '.gitignore',
        'tools\build.ps1',
        'tools\validate.ps1',
        'tools\sync-update-check.ps1',
        '.github\workflows\validate.yml'
    )
    foreach ($relativePath in $requiredRootFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $rootPath $relativePath) -PathType Leaf)) {
            Add-Issue -Issues $issues -Code 'ROOT_FILE_MISSING' -Path $relativePath -Message 'Required repository file is missing.'
        }
    }

    $versionPath = Join-Path $rootPath 'VERSION'
    $version = $null
    if (Test-Path -LiteralPath $versionPath -PathType Leaf) {
        $version = (Read-Utf8 -Path $versionPath).Trim()
        if ($version -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
            Add-Issue -Issues $issues -Code 'VERSION_INVALID' -Path 'VERSION' -Message 'VERSION must contain semantic version text.'
        }
    }
    $updateContract = Get-UpdateContract -Root $rootPath -Issues $issues

    foreach ($readmeName in @('README.md', 'README.en.md')) {
        $readmePath = Join-Path $rootPath $readmeName
        foreach ($requiredPattern in @(
            'AIBP',
            'AI Business Partner',
            'core',
            '(?m)\|\s*`ecommerce`\s*\|',
            'tooling',
            'Source Available',
            'Not Open Source',
            'sg-aibp',
            '\u89c4\u5212|planned'
        )) {
            Require-Pattern -Issues $issues -Path $readmePath -Code 'README_CONTENT' -Pattern $requiredPattern -Message "README is missing required AIBP content: $requiredPattern"
        }
        $readmeContent = Read-Utf8 -Path $readmePath
        if ($readmeContent -match '`commerce`|skills/commerce') {
            Add-Issue -Issues $issues -Code 'LEGACY_TRACK' -Path $readmeName -Message 'README still uses the retired commerce track label.'
        }
    }
    Require-Pattern -Issues $issues -Path (Join-Path $rootPath 'LICENSE') -Code 'LICENSE_CONTENT' -Pattern 'Source Available' -Message 'License must preserve the source-available intent.'
    Require-Pattern -Issues $issues -Path (Join-Path $rootPath 'LICENSE') -Code 'LICENSE_CONTENT' -Pattern '\u81ea\u8eab\u7ecf\u8425' -Message 'License must cover the user or organization own operations.'
    Require-Pattern -Issues $issues -Path (Join-Path $rootPath 'LICENSE') -Code 'LICENSE_CONTENT' -Pattern 'Skill/Agent' -Message 'License must cover internal Skill/Agent construction.'
    Require-Pattern -Issues $issues -Path (Join-Path $rootPath 'LICENSE') -Code 'LICENSE_CONTENT' -Pattern '\u5f8b\u5e08\u590d\u6838|\u6267\u4e1a\u5f8b\u5e08\u590d\u6838' -Message 'License must retain the counsel-review statement.'
    if ($version) {
        Require-Pattern -Issues $issues -Path (Join-Path $rootPath 'CHANGELOG.md') -Code 'CHANGELOG_CONTENT' -Pattern ([regex]::Escape($version)) -Message 'CHANGELOG must describe the VERSION release.'
    }

    $skillsRoot = Join-Path $rootPath 'skills'
    if (-not (Test-Path -LiteralPath $skillsRoot -PathType Container)) {
        Add-Issue -Issues $issues -Code 'SKILLS_ROOT_MISSING' -Path 'skills' -Message 'skills directory is missing.'
        return $issues
    }

    $nestedSkillFiles = @(
        Get-ChildItem -LiteralPath $skillsRoot -Recurse -Filter 'SKILL.md' -File |
            Where-Object {
                $_.FullName -notmatch '\\tests\\fixtures\\' -and
                $_.Directory.Parent.FullName -ne $skillsRoot
            }
    )
    foreach ($nestedSkillFile in $nestedSkillFiles) {
        $relativeNested = $nestedSkillFile.FullName.Substring($rootPath.Length).TrimStart('\')
        Add-Issue -Issues $issues -Code 'NESTED_SKILL' -Path $relativeNested -Message 'Skill directories must be flat at skills/<slug>.'
    }

    $skillDirs = @(Get-ChildItem -LiteralPath $skillsRoot -Directory | Sort-Object Name)
    if ($skillDirs.Count -eq 0) {
        Add-Issue -Issues $issues -Code 'SKILL_SET_EMPTY' -Path 'skills' -Message 'At least one direct Skill directory is required.'
    }

    foreach ($skillDir in $skillDirs) {
        $skillName = $skillDir.Name
        $relativeSkill = "skills\$skillName"
        $skillFile = Join-Path $skillDir.FullName 'SKILL.md'
        if ($skillName -notmatch '^sg-[a-z0-9]+(?:-[a-z0-9]+)*$') {
            Add-Issue -Issues $issues -Code 'SKILL_SLUG' -Path $relativeSkill -Message 'Skill slug must use lowercase sg- kebab-case.'
        }
        if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
            Add-Issue -Issues $issues -Code 'SKILL_FILE_MISSING' -Path $relativeSkill -Message 'Direct Skill directory requires SKILL.md.'
            continue
        }
        Test-SkillUpdateContract -Issues $issues -SkillPath $skillDir.FullName -RelativeSkill $relativeSkill -Version $version -Contract $updateContract

        foreach ($item in Get-ChildItem -LiteralPath $skillDir.FullName -Force) {
            if (@('SKILL.md', 'SKILL.patch.md', 'agents', 'references', 'scripts', 'assets', 'tests') -notcontains $item.Name) {
                Add-Issue -Issues $issues -Code 'RUNTIME_ITEM_UNEXPECTED' -Path "$relativeSkill\$($item.Name)" -Message 'Unexpected Skill-root item.'
            }
        }
        foreach ($docName in @('README.md', 'QUICKREF.md', 'CHANGELOG.md')) {
            if (Test-Path -LiteralPath (Join-Path $skillDir.FullName $docName)) {
                Add-Issue -Issues $issues -Code 'RUNTIME_DOC_PRESENT' -Path "$relativeSkill\$docName" -Message 'Repository documentation must stay outside the runtime Skill.'
            }
        }
        foreach ($directory in Get-ChildItem -LiteralPath $skillDir.FullName -Recurse -Directory) {
            if (
                $directory.Parent.Name -eq $directory.Name -and
                $directory.Name -in @('agents', 'assets', 'references', 'scripts', 'tests')
            ) {
                $relativeDuplicate = $directory.FullName.Substring($rootPath.Length).TrimStart('\')
                Add-Issue -Issues $issues -Code 'DUPLICATE_NESTING' -Path $relativeDuplicate -Message 'Duplicate nested runtime directory is forbidden.'
            }
        }

        $frontmatter = Get-Frontmatter -Path $skillFile
        if ($null -eq $frontmatter) {
            Add-Issue -Issues $issues -Code 'FRONTMATTER_INVALID' -Path "$relativeSkill\SKILL.md" -Message 'Frontmatter is missing or invalid.'
            continue
        }
        foreach ($key in $frontmatter.Fields.Keys) {
            if (@('name', 'description', 'license') -notcontains $key) {
                Add-Issue -Issues $issues -Code 'FRONTMATTER_KEY' -Path "$relativeSkill\SKILL.md" -Message "Unexpected frontmatter key: $key"
            }
        }
        foreach ($key in @('name', 'description', 'license')) {
            if (
                -not $frontmatter.Fields.Contains($key) -or
                [string]::IsNullOrWhiteSpace([string]$frontmatter.Fields[$key])
            ) {
                Add-Issue -Issues $issues -Code 'FRONTMATTER_REQUIRED' -Path "$relativeSkill\SKILL.md" -Message "Missing frontmatter key: $key"
            }
        }
        if (
            $frontmatter.Fields.Contains('name') -and
            $frontmatter.Fields['name'] -ne $skillName
        ) {
            Add-Issue -Issues $issues -Code 'SKILL_NAME' -Path "$relativeSkill\SKILL.md" -Message 'Frontmatter name must equal its directory.'
        }
        if ($frontmatter.Fields.Contains('description')) {
            Test-DescriptionNarrative -Issues $issues -RelativePath "$relativeSkill\SKILL.md" -Description ([string]$frontmatter.Fields['description'])
        }

        $referencedPaths = @(
            [regex]::Matches(
                $frontmatter.Content,
                '(?:references|scripts|assets)/[A-Za-z0-9._/-]+'
            ) |
                ForEach-Object { $_.Value } |
                Sort-Object -Unique
        )
        foreach ($referencedPath in $referencedPaths) {
            if ($referencedPath.Contains('..')) {
                Add-Issue -Issues $issues -Code 'REFERENCE_TRAVERSAL' -Path "$relativeSkill\SKILL.md" -Message "Unsafe referenced path: $referencedPath"
                continue
            }
            $platformPath = $referencedPath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
            if (-not (Test-Path -LiteralPath (Join-Path $skillDir.FullName $platformPath) -PathType Leaf)) {
                Add-Issue -Issues $issues -Code 'REFERENCE_MISSING' -Path "$relativeSkill\SKILL.md" -Message "Referenced file does not exist: $referencedPath"
            }
        }

        $openaiPath = Join-Path $skillDir.FullName 'agents\openai.yaml'
        if (-not (Test-Path -LiteralPath $openaiPath -PathType Leaf)) {
            Add-Issue -Issues $issues -Code 'OPENAI_YAML_MISSING' -Path "$relativeSkill\agents\openai.yaml" -Message 'Agent interface metadata is required.'
        }
        else {
            foreach ($pattern in @('display_name:', 'short_description:', [regex]::Escape('$' + $skillName))) {
                Require-Pattern -Issues $issues -Path $openaiPath -Code 'OPENAI_YAML_CONTENT' -Pattern $pattern -Message "Agent metadata is missing: $pattern"
            }
        }

        $runnerPath = Join-Path $skillDir.FullName 'scripts\run_eval.py'
        $fixtureRoot = Join-Path $skillDir.FullName 'tests\fixtures'
        if (Test-Path -LiteralPath $runnerPath -PathType Leaf) {
            if (-not (Test-Path -LiteralPath $fixtureRoot -PathType Container)) {
                Add-Issue -Issues $issues -Code 'RUNNER_FIXTURES_MISSING' -Path "$relativeSkill\tests\fixtures" -Message 'A packaged eval runner requires packaged fixtures.'
            }
            else {
                $goldenCases = @(
                    Get-ChildItem -LiteralPath $fixtureRoot -Directory |
                        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'case.json') -PathType Leaf }
                )
                if ($goldenCases.Count -eq 0) {
                    Add-Issue -Issues $issues -Code 'RUNNER_FIXTURES_EMPTY' -Path "$relativeSkill\tests\fixtures" -Message 'Eval runner fixtures contain no case.json files.'
                }
            }
        }

        $repoTestPath = Join-Path $rootPath "tests\$skillName"
        if (
            -not (Test-Path -LiteralPath $repoTestPath -PathType Container) -and
            -not (Test-Path -LiteralPath $runnerPath -PathType Leaf)
        ) {
            Add-Issue -Issues $issues -Code 'EVAL_MISSING' -Path "tests\$skillName" -Message 'Each Skill requires repository tests or a self-contained eval runner.'
        }
        $casesPath = Join-Path $repoTestPath 'cases.json'
        if (Test-Path -LiteralPath $casesPath -PathType Leaf) {
            try {
                $cases = @(ConvertFrom-Json -InputObject (Read-Utf8 -Path $casesPath))
                $ids = @($cases | ForEach-Object { $_.id })
                if ($cases.Count -eq 0) {
                    Add-Issue -Issues $issues -Code 'EVAL_COUNT' -Path "tests\$skillName\cases.json" -Message 'cases.json must contain at least one case.'
                }
                if (@($ids | Sort-Object -Unique).Count -ne $ids.Count) {
                    Add-Issue -Issues $issues -Code 'EVAL_DUPLICATE' -Path "tests\$skillName\cases.json" -Message 'Case ids must be unique.'
                }
            }
            catch {
                Add-Issue -Issues $issues -Code 'EVAL_JSON' -Path "tests\$skillName\cases.json" -Message $_.Exception.Message
            }
        }

        foreach ($readmeName in @('README.md', 'README.en.md')) {
            $readmePath = Join-Path $rootPath $readmeName
            Require-Pattern -Issues $issues -Path $readmePath -Code 'README_SKILL_PATH' -Pattern ([regex]::Escape("skills/$skillName")) -Message "README must include exact local path for $skillName."
            Require-Pattern -Issues $issues -Path $readmePath -Code 'README_SKILL_PATH' -Pattern ([regex]::Escape("github.com/sgskills/aibp/tree/main/skills/$skillName")) -Message "README must include planned exact repository path for $skillName."
        }
    }

    $legacyPrefix = 'sg' + 's-'
    $allowedLegacyFiles = @('README.md', 'README.en.md', 'CHANGELOG.md')
    $scanFiles = @(
        Get-ChildItem -LiteralPath $rootPath -Recurse -File |
            Where-Object {
                $_.FullName -notmatch '\\.git\\|\\.work\\|\\dist\\' -and
                $_.Extension -in @('.md', '.yaml', '.yml', '.json', '.ps1', '.py', '.html', '.txt')
            }
    )
    foreach ($file in $scanFiles) {
        $relative = $file.FullName.Substring($rootPath.Length).TrimStart('\')
        $content = Read-Utf8 -Path $file.FullName
        if (
            ($relative.Contains($legacyPrefix) -or $content.Contains($legacyPrefix)) -and
            $allowedLegacyFiles -notcontains $relative
        ) {
            Add-Issue -Issues $issues -Code 'LEGACY_PREFIX' -Path $relative -Message 'Legacy prefix is allowed only in migration notes.'
        }
        $bannedPhrases = @(
            [regex]::Unescape('CEO \u7684\u773c\u5149'),
            [regex]::Unescape('CEO\u7684\u773c\u5149'),
            [regex]::Unescape('\u7535\u5546\u8fd0\u8425\u95ee\u9898\u7ed3\u6784\u5316\u62c6\u89e3\u987e\u95ee')
        )
        foreach ($bannedPhrase in $bannedPhrases) {
            if ($content.Contains($bannedPhrase)) {
                Add-Issue -Issues $issues -Code 'BANNED_PHRASE' -Path $relative -Message "Obsolete display name found: $bannedPhrase"
            }
        }
    }
    return $issues
}

function Assert-ContainsCode {
    param(
        [object[]]$Issues,
        [string]$ExpectedCode,
        [string]$Label
    )

    if (@($Issues | ForEach-Object { $_.Code }) -notcontains $ExpectedCode) {
        throw "$Label did not trigger $ExpectedCode. Got: $((@($Issues | ForEach-Object { $_.Code } | Sort-Object -Unique)) -join ', ')"
    }
}

function Invoke-GateCommand {
    param(
        [string]$Script,
        [string]$FixtureRoot,
        [string]$EvidencePath
    )

    $previousPreference = $ErrorActionPreference
    try {
        # A failing native command is the expected evidence for the red fixtures.
        $ErrorActionPreference = 'Continue'
        $output = @(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script -RepoRoot $FixtureRoot 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    $lines = @($output | ForEach-Object { [string]$_ })
    Write-Utf8 -Path $EvidencePath -Content ((@("exit_code=$exitCode") + $lines) -join "`n")
    return [PSCustomObject]@{ ExitCode = $exitCode; Output = $lines }
}

function Assert-ExtensionPackages {
    param(
        [string]$FixtureRoot,
        [string]$ProbeName,
        [string]$Version
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $skillDirs = @(
        Get-ChildItem -LiteralPath (Join-Path $FixtureRoot 'skills') -Directory |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') -PathType Leaf }
    )
    $distPath = Join-Path $FixtureRoot 'dist'
    $zipFiles = @(Get-ChildItem -LiteralPath $distPath -File -Filter '*.zip')
    if ($zipFiles.Count -ne ($skillDirs.Count + 1)) {
        throw 'Extension build did not create one ZIP per discovered Skill plus one bundle.'
    }
    $checksums = @([System.IO.File]::ReadAllLines((Join-Path $distPath 'SHA256SUMS.txt')) | Where-Object { $_.Trim() })
    if ($checksums.Count -ne $zipFiles.Count) {
        throw 'Extension build checksum count does not match its ZIP count.'
    }
    foreach ($zipFile in $zipFiles) {
        $expected = '{0}  {1}' -f (Get-FileHash -LiteralPath $zipFile.FullName -Algorithm SHA256).Hash, $zipFile.Name
        if ($checksums -notcontains $expected) {
            throw "Extension build checksum is missing or incorrect: $($zipFile.Name)"
        }
    }
    $requiredEntries = @('SKILL.md', 'scripts/check-update.ps1', 'scripts/check-update.sh', 'scripts/update-version.txt')
    foreach ($zipName in @("$ProbeName-$Version.zip", "aibp-$Version.zip")) {
        $archive = [System.IO.Compression.ZipFile]::OpenRead((Join-Path $distPath $zipName))
        try {
            foreach ($relative in $requiredEntries) {
                $entry = $archive.GetEntry("$ProbeName/$relative")
                if ($null -eq $entry) {
                    throw "Extension package is missing $ProbeName/$relative in $zipName."
                }
                $reader = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
                try {
                    $actual = Normalize-LineEndings -Content $reader.ReadToEnd()
                }
                finally {
                    $reader.Dispose()
                }
                $sourcePath = Join-Path (Join-Path $FixtureRoot "skills\$ProbeName") $relative.Replace('/', '\')
                $expected = Normalize-LineEndings -Content (Read-Utf8 -Path $sourcePath)
                if ($actual -cne $expected) {
                    throw "Extension package entry differs from its validated source: $ProbeName/$relative"
                }
            }
        }
        finally {
            $archive.Dispose()
        }
    }
    Write-Output "FIFTH_SKILL_BUILD_GREEN PASS: $($skillDirs.Count) Skills, $($zipFiles.Count) ZIPs, $($checksums.Count) verified SHA256 lines; standalone and bundle entry/runtime files match."
}

function Invoke-ValidatorSelfTest {
    param([string]$SourceRoot)

    $sourceIssues = @(Invoke-RepoValidation -Root $SourceRoot)
    if ($sourceIssues.Count -gt 0) {
        throw "Self-test requires a valid repository. Got: $((@($sourceIssues.Code | Sort-Object -Unique)) -join ', ')"
    }

    $sourcePath = (Resolve-Path -LiteralPath $SourceRoot).Path
    $version = (Read-Utf8 -Path (Join-Path $sourcePath 'VERSION')).Trim()
    $testRoot = Join-Path $sourcePath ".work\$version\gate-tests"
    $runRoot = Join-Path $testRoot ('validator-' + [guid]::NewGuid().ToString('N'))
    $fixtureRoot = Join-Path $runRoot 'repo'
    $fixtureTemp = Join-Path $runRoot 'tmp'
    $evidenceRoot = Join-Path $runRoot 'evidence'
    $previousTemp = $env:TEMP
    $previousTmp = $env:TMP
    $previousTmpDir = $env:TMPDIR
    try {
        [void][System.IO.Directory]::CreateDirectory($fixtureRoot)
        [void][System.IO.Directory]::CreateDirectory($fixtureTemp)
        [void][System.IO.Directory]::CreateDirectory($evidenceRoot)
        $env:TEMP = $fixtureTemp
        $env:TMP = $fixtureTemp
        $env:TMPDIR = $fixtureTemp
        foreach ($fileName in @('README.md', 'README.en.md', 'AGENTS.md', 'LICENSE', 'VERSION', 'CHANGELOG.md', '.gitignore')) {
            Copy-Item -LiteralPath (Join-Path $SourceRoot $fileName) -Destination $fixtureRoot
        }
        foreach ($directoryName in @('.github', 'skills', 'tests', 'tools')) {
            Copy-Item -LiteralPath (Join-Path $SourceRoot $directoryName) -Destination $fixtureRoot -Recurse
        }

        $probeName = 'sg-extension-probe'
        $probeSkill = Join-Path $fixtureRoot "skills\$probeName"
        $probeAgents = Join-Path $probeSkill 'agents'
        $probeTests = Join-Path $fixtureRoot "tests\$probeName"
        [void][System.IO.Directory]::CreateDirectory($probeAgents)
        [void][System.IO.Directory]::CreateDirectory($probeTests)
        Write-Utf8 -Path (Join-Path $probeSkill 'SKILL.md') -Content @'
---
name: sg-extension-probe
description: |
  Converts a bounded business input into a small, verifiable extension result.
  Use when validating dynamic Skill discovery; not for unrelated production work.
license: SGSkills Internal Use License 1.0
---

# Extension Probe

Return a reversible local result. Do not perform external actions.
'@
        Write-Utf8 -Path (Join-Path $probeAgents 'openai.yaml') -Content @'
interface:
  display_name: "Extension Probe"
  short_description: "Validates dynamic discovery"
  default_prompt: "Use $sg-extension-probe for the extension validation fixture."
'@
        Write-Utf8 -Path (Join-Path $probeTests 'cases.json') -Content '[{"id":"extension-probe","category":"extension"}]'
        foreach ($readmeName in @('README.md', 'README.en.md')) {
            $readmePath = Join-Path $fixtureRoot $readmeName
            $readmeText = Read-Utf8 -Path $readmePath
            $readmeText += "`n- skills/$probeName`n- https://github.com/sgskills/aibp/tree/main/skills/$probeName`n"
            Write-Utf8 -Path $readmePath -Content $readmeText
        }

        $extensionRed = @(Invoke-RepoValidation -Root $fixtureRoot)
        Assert-ContainsCode -Issues $extensionRed -ExpectedCode 'UPDATE_FILE_MISSING' -Label 'Unconfigured extension update files'
        Assert-ContainsCode -Issues $extensionRed -ExpectedCode 'UPDATE_ENTRY_MISSING' -Label 'Unconfigured extension entry'
        $fixtureValidator = Join-Path $fixtureRoot 'tools\validate.ps1'
        $fixtureBuild = Join-Path $fixtureRoot 'tools\build.ps1'
        $redValidation = Invoke-GateCommand -Script $fixtureValidator -FixtureRoot $fixtureRoot -EvidencePath (Join-Path $evidenceRoot 'validator-red.txt')
        if ($redValidation.ExitCode -eq 0 -or ($redValidation.Output -join "`n") -notmatch '\[UPDATE_FILE_MISSING\]') {
            throw 'Unconfigured extension must make the real validator process exit nonzero with UPDATE_FILE_MISSING.'
        }
        Write-Output "EXPECTED RED: missing update-check files; validator exit=$($redValidation.ExitCode)"

        $fixtureDist = Join-Path $fixtureRoot 'dist'
        [void][System.IO.Directory]::CreateDirectory($fixtureDist)
        $sentinelPath = Join-Path $fixtureDist 'preserve-on-validation-failure.txt'
        $sentinelContent = 'An invalid source tree must not delete the existing dist.'
        Write-Utf8 -Path $sentinelPath -Content $sentinelContent
        $redBuild = Invoke-GateCommand -Script $fixtureBuild -FixtureRoot $fixtureRoot -EvidencePath (Join-Path $evidenceRoot 'build-red.txt')
        if ($redBuild.ExitCode -eq 0 -or ($redBuild.Output -join "`n") -notmatch '\[UPDATE_FILE_MISSING\]') {
            throw 'Unconfigured extension must stop the real build at repository validation.'
        }
        if (-not (Test-Path -LiteralPath $sentinelPath -PathType Leaf) -or (Read-Utf8 -Path $sentinelPath) -cne $sentinelContent) {
            throw 'Failed validation changed or deleted the existing dist sentinel.'
        }
        if (@(Get-ChildItem -LiteralPath $fixtureDist -Force).Count -ne 1) {
            throw 'Failed validation wrote unexpected build artifacts.'
        }
        if (Test-Path -LiteralPath (Join-Path $probeSkill 'scripts\check-update.ps1')) {
            throw 'Validation or build silently repaired the missing update-check files.'
        }
        Write-Output "EXPECTED RED: update-check build gate; build exit=$($redBuild.ExitCode); dist sentinel unchanged"

        $syncResult = Invoke-GateCommand -Script (Join-Path $fixtureRoot 'tools\sync-update-check.ps1') -FixtureRoot $fixtureRoot -EvidencePath (Join-Path $evidenceRoot 'sync-green.txt')
        if ($syncResult.ExitCode -ne 0) {
            throw "Explicit sync failed in the extension fixture: $($syncResult.Output -join ' ')"
        }
        $extensionGreen = @(Invoke-RepoValidation -Root $fixtureRoot)
        if ($extensionGreen.Count -gt 0) {
            throw "Fifth-Skill extension fixture failed: $((@($extensionGreen | ForEach-Object { $_.Code + ':' + $_.Path })) -join ', ')"
        }
        Write-Output 'FIFTH_SKILL_GREEN PASS'
        $greenValidation = Invoke-GateCommand -Script $fixtureValidator -FixtureRoot $fixtureRoot -EvidencePath (Join-Path $evidenceRoot 'validator-green.txt')
        if ($greenValidation.ExitCode -ne 0) {
            throw "Configured extension failed the real validator: $($greenValidation.Output -join ' ')"
        }
        $greenBuild = Invoke-GateCommand -Script $fixtureBuild -FixtureRoot $fixtureRoot -EvidencePath (Join-Path $evidenceRoot 'build-green.txt')
        if ($greenBuild.ExitCode -ne 0) {
            throw "Configured extension failed the real build: $($greenBuild.Output -join ' ')"
        }
        Assert-ExtensionPackages -FixtureRoot $fixtureRoot -ProbeName $probeName -Version $version
        Write-Output "UPDATE_CHECK_GATE_EVIDENCE: $evidenceRoot"

        $readmePath = Join-Path $fixtureRoot 'README.md'
        $currentReadme = Read-Utf8 -Path $readmePath
        $legacyReadme = $currentReadme.Replace('`ecommerce`', '`commerce`').Replace('skills/ecommerce', 'skills/commerce')
        Write-Utf8 -Path $readmePath -Content $legacyReadme
        $legacyTrackIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
        Assert-ContainsCode -Issues $legacyTrackIssues -ExpectedCode 'LEGACY_TRACK' -Label 'Legacy commerce track fixture'
        Write-Output 'EXPECTED RED: legacy commerce track'
        Write-Utf8 -Path $readmePath -Content $currentReadme

        $missingSkillDir = Join-Path $fixtureRoot 'skills\sg-missing-probe'
        [void][System.IO.Directory]::CreateDirectory($missingSkillDir)
        $missingIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
        Assert-ContainsCode -Issues $missingIssues -ExpectedCode 'SKILL_FILE_MISSING' -Label 'Missing SKILL fixture'
        Write-Output 'EXPECTED RED: missing SKILL.md'
        Remove-Item -LiteralPath $missingSkillDir -Recurse -Force

        $nestedSkillDir = Join-Path $fixtureRoot 'skills\core\sg-nested-probe'
        [void][System.IO.Directory]::CreateDirectory($nestedSkillDir)
        Write-Utf8 -Path (Join-Path $nestedSkillDir 'SKILL.md') -Content "---`nname: sg-nested-probe`ndescription: Nested probe converts input to output. Use when testing; not for production.`nlicense: test`n---`n"
        $nestedIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
        Assert-ContainsCode -Issues $nestedIssues -ExpectedCode 'NESTED_SKILL' -Label 'Nested Skill fixture'
        Write-Output 'EXPECTED RED: nested Skill directory'
        Remove-Item -LiteralPath (Join-Path $fixtureRoot 'skills\core') -Recurse -Force

        $badSkillDir = Join-Path $fixtureRoot 'skills\sg-bad-frontmatter'
        [void][System.IO.Directory]::CreateDirectory($badSkillDir)
        Write-Utf8 -Path (Join-Path $badSkillDir 'SKILL.md') -Content "---`nname: [unterminated`ndescription: broken`n---`n"
        $badIssues = @(Invoke-RepoValidation -Root $fixtureRoot)
        Assert-ContainsCode -Issues $badIssues -ExpectedCode 'FRONTMATTER_INVALID' -Label 'Bad frontmatter fixture'
        Write-Output 'EXPECTED RED: bad frontmatter'
        Remove-Item -LiteralPath $badSkillDir -Recurse -Force

        $recovered = @(Invoke-RepoValidation -Root $fixtureRoot)
        if ($recovered.Count -gt 0) {
            throw "Self-test fixture did not recover: $((@($recovered | ForEach-Object { $_.Code + ':' + $_.Path })) -join ', ')"
        }
        Write-Output 'SELF-TEST PASS'
    }
    finally {
        $env:TEMP = $previousTemp
        $env:TMP = $previousTmp
        $env:TMPDIR = $previousTmpDir
        $allowedPrefix = [System.IO.Path]::GetFullPath($runRoot).TrimEnd('\') + '\'
        foreach ($cleanupPath in @($fixtureRoot, $fixtureTemp)) {
            if (Test-Path -LiteralPath $cleanupPath) {
                $resolvedCleanup = (Resolve-Path -LiteralPath $cleanupPath).Path
                if (-not $resolvedCleanup.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    throw 'Refusing to remove a gate fixture outside its repository-local run directory.'
                }
                Remove-Item -LiteralPath $resolvedCleanup -Recurse -Force
            }
        }
    }
}

if ($SelfTest) {
    Invoke-ValidatorSelfTest -SourceRoot $RepoRoot
    exit 0
}

$validationIssues = @(Invoke-RepoValidation -Root $RepoRoot)
if ($validationIssues.Count -gt 0) {
    Write-Output "VALIDATION FAILED: $($validationIssues.Count) issue(s)"
    $validationIssues |
        Sort-Object Code, Path |
        ForEach-Object {
            Write-Output ("[{0}] {1} :: {2}" -f $_.Code, $_.Path, $_.Message)
        }
    exit 1
}

Write-Output 'VALIDATION PASS'
