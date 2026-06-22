// Vocab Sheet Spell-Check — Google Apps Script
//
// Registers an installable onEdit trigger that calls the LanguageTool free
// REST API on every column A edit. Corrects spelling errors (including missing
// accents) in-place and records the original value as a cell note.
//
// SETUP: Run createTrigger() once from Extensions > Apps Script to register
// the installable trigger. Simple onEdit cannot call UrlFetchApp — the
// installable trigger is required.

var COL_VOCAB       = 1; // Column A — word input
var COL_TRANSLATION = 2; // Column B — GOOGLETRANSLATE formula
var COL_LANG        = 3; // Column C — detected language code ('es' or 'en')

/**
 * Build the GOOGLETRANSLATE formula for a given row.
 * Translates col A → col B based on the language code in col C:
 *   col C = "es" → source is Spanish, target is English
 *   col C = "en" → source is English, target is Spanish
 */
function translateFormula(row) {
  return '=IF(A' + row + '="","",IFERROR(GOOGLETRANSLATE(A' + row + ',C' + row + ',IF(C' + row + '="es","en","es")),"))';
}

/**
 * Run once to register the installable onEdit trigger pointing at handleEdit.
 * Guards against duplicate registration by checking existing triggers first.
 */
function createTrigger() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  var existing = ScriptApp.getUserTriggers(ss);
  for (var i = 0; i < existing.length; i++) {
    if (existing[i].getHandlerFunction() === 'handleEdit') {
      Logger.log('Trigger already exists for handleEdit — skipping creation');
      return;
    }
  }

  ScriptApp.newTrigger('handleEdit')
    .forSpreadsheet(ss)
    .onEdit()
    .create();
  Logger.log('Trigger created: handleEdit fires on sheet edits');
}

/**
 * Installable onEdit trigger handler. Do not rename to onEdit — that would
 * register it as a simple trigger, which cannot call UrlFetchApp.
 *
 * @param {Object} e - Apps Script edit event object
 */
function handleEdit(e) {
  var range = e.range;

  // Act only on column A (1-based index)
  if (range.getColumn() !== COL_VOCAB) return;

  // For single-cell edits, use the edited range.
  // For bulk pastes (numRows > 1), correct only the first row.
  var cell;
  if (range.getNumRows() === 1) {
    cell = range;
  } else {
    cell = range.getSheet().getRange(range.getRow(), COL_VOCAB);
  }

  var originalText = cell.getValue();
  if (typeof originalText !== 'string' || originalText.trim() === '') return;

  var row = cell.getRow();
  var sheet = cell.getSheet();
  if (row < 2) return; // Skip header row — never overwrite col B/C headers

  var result;
  var detectedLang;

  if (/[ñáéíóúüÁÉÍÓÚÜ¿¡]/.test(originalText)) {
    // Spanish diacritics present — unambiguously Spanish. Call LT es only.
    result = callLanguageTool(originalText, 'es');
    if (!result) return;
    detectedLang = 'es';
  } else {
    // No diacritics — call both endpoints and use the zero-match oracle.
    var esResult = callLanguageTool(originalText, 'es');
    var enResult = callLanguageTool(originalText, 'en-US');
    if (!esResult && !enResult) return;
    var detected = detectLanguage(originalText, esResult, enResult);
    detectedLang = detected.lang;
    result = detected.result;
    if (!result) return;
  }

  // Write detected language to column C.
  // Skip the write when a multi-column paste already populated col C so we
  // don't overwrite the user's pasted value. For single-col edits (the common
  // case) range.getLastColumn() === 1 < 3, so the write always fires.
  try {
    if (range.getLastColumn() < COL_LANG) {
      sheet.getRange(row, COL_LANG).setValue(detectedLang);
    }
  } catch (err) {
    Logger.log('handleEdit: col C write failed: ' + err.message);
  }

  // Write GOOGLETRANSLATE formula to column B if currently empty.
  // This write happens unconditionally (before the spelling-correction check)
  // so that correctly-spelled words (spellingMatches.length === 0) also get
  // their translation formula — not just words that needed correction.
  // Check both getValue() and getFormula() so we don't overwrite a custom
  // formula that currently evaluates to empty because col A was just filled.
  try {
    var bCell = sheet.getRange(row, COL_TRANSLATION);
    if (bCell.getValue() === '' && bCell.getFormula() === '') {
      bCell.setFormula(translateFormula(row));
    }
  } catch (err) {
    Logger.log('handleEdit: col B write failed: ' + err.message);
  }

  // Accept spelling errors and typographical errors (accent placement).
  // "misspelling"   = wrong letters: covencion, caida (changes word meaning).
  // "typographical" = accent only:   ultimamente → últimamente.
  // Grammar, style, and punctuation are excluded; the PUNCTUATION and
  // TYPOGRAPHY categories are also disabled at the API level.
  var spellingMatches = (result.matches || []).filter(isSpellingIssue);

  if (spellingMatches.length === 0) return;

  // Apply corrections in reverse offset order so earlier character positions
  // remain valid as each substitution changes the string length.
  spellingMatches.sort(function(a, b) { return b.offset - a.offset; });

  var correctedText = originalText;
  spellingMatches.forEach(function(match) {
    correctedText = correctedText.slice(0, match.offset) +
                    match.replacements[0].value +
                    correctedText.slice(match.offset + match.length);
  });

  // Preserve original first-character case. LanguageTool treats single words
  // as sentence starts and may capitalize them even when the input was lowercase.
  if (correctedText.length > 0 && originalText.length > 0) {
    var origFirst = originalText[0];
    var corrFirst = correctedText[0];
    if (origFirst === origFirst.toLowerCase() && corrFirst === corrFirst.toUpperCase()) {
      correctedText = corrFirst.toLowerCase() + correctedText.slice(1);
    }
  }

  if (correctedText !== originalText) {
    try {
      cell.setNote(originalText);
      cell.setValue(correctedText);
    } catch (err) {
      Logger.log('handleEdit: correction write failed: ' + err.message);
    }
  }
}

/**
 * Given two LanguageTool results, return the one whose first correction
 * is closer (edit distance) to the original text. Prefers a result with
 * corrections over one without.
 */
function closerResult(original, r1, r2) {
  var c1 = firstCorrectedText(original, r1);
  var c2 = firstCorrectedText(original, r2);
  if (!c1 && !c2) return null;
  if (!c1) return r2;
  if (!c2) return r1;
  return editDistance(original, c1) <= editDistance(original, c2) ? r1 : r2;
}

/**
 * Apply the first spelling/typographical match from a result and return the
 * corrected text, for use in edit-distance comparison only.
 */
function firstCorrectedText(original, result) {
  if (!result) return null;
  var matches = (result.matches || []).filter(isSpellingIssue);
  if (!matches.length) return null;
  var m = matches.sort(function(a, b) { return b.offset - a.offset; })[0];
  return original.slice(0, m.offset) + m.replacements[0].value + original.slice(m.offset + m.length);
}

/**
 * Levenshtein edit distance between two strings.
 */
function editDistance(a, b) {
  var m = a.length, n = b.length, i, j;
  var row = [];
  for (j = 0; j <= n; j++) row[j] = j;
  for (i = 1; i <= m; i++) {
    var prev = i;
    for (j = 1; j <= n; j++) {
      var val = a[i - 1] === b[j - 1]
        ? row[j - 1]
        : 1 + Math.min(row[j], prev, row[j - 1]);
      row[j - 1] = prev;
      prev = val;
    }
    row[n] = prev;
  }
  return row[n];
}

/**
 * POST to the LanguageTool free REST API.
 *
 * @param {string} text - Text to check
 * @param {string} language - Language code ('es', 'en-US', etc.)
 * @returns {Object|null} Parsed JSON response, or null on any error
 */
function callLanguageTool(text, language) {
  var payload = {
    text: text,
    language: language,
    disabledCategories: 'PUNCTUATION,TYPOGRAPHY'
  };

  var options = {
    method: 'post',
    payload: payload,
    muteHttpExceptions: true
  };

  try {
    var response = UrlFetchApp.fetch(
      'https://api.languagetool.org/v2/check',
      options
    );
    if (response.getResponseCode() !== 200) {
      Logger.log('LanguageTool ' + language + ' HTTP ' + response.getResponseCode());
      return null;
    }
    return JSON.parse(response.getContentText());
  } catch (err) {
    Logger.log('LanguageTool ' + language + ' fetch error: ' + err.message);
    return null;
  }
}

/**
 * Returns true for matches that count as a detection signal — any
 * misspelling/typographical flag regardless of replacement length.
 *
 * The length guard is intentionally absent here: a short-replacement suggestion
 * (e.g. LT es proposing "hoy" for "however", 3 < 7) still signals that the word
 * does not belong to that language and should count for detection, even though it
 * would be rejected by isSpellingIssue as a correction.
 */
function isDetectionIssue(m) {
  return m.rule &&
    (m.rule.issueType === 'misspelling' || m.rule.issueType === 'typographical') &&
    m.replacements && m.replacements.length > 0;
}

/**
 * Returns true for matches that represent a genuine spelling or accent error
 * AND whose replacement is at least as long as the original span. The length
 * guard prevents applying shortening corrections (e.g. "lucido"→"lucid").
 * Used by spellingMatches and firstCorrectedText.
 *
 * Intentional divergence from isDetectionIssue: detection counts short-replacement
 * foreign-word flags as signals; correction must not apply them.
 */
function isSpellingIssue(m) {
  return isDetectionIssue(m) && m.replacements[0].value.length >= m.length;
}

/**
 * Determine language from LanguageTool results.
 *
 * Uses isDetectionIssue (no length guard) for counting matches so that
 * short-replacement foreign-word flags still count as detection signals.
 * Uses isSpellingIssue (length-guarded) inside the edit-distance discriminator
 * so the measured distance reflects a correction that would actually be applied.
 *
 * @param {string} text - Original text
 * @param {Object|null} esResult - LT response for 'es'
 * @param {Object|null} enResult - LT response for 'en-US'
 * @returns {{lang: string, result: Object}} Detected language and result to use for correction
 */
function detectLanguage(text, esResult, enResult) {
  var esMatches = esResult ? (esResult.matches || []).filter(isDetectionIssue) : null;
  var enMatches = enResult ? (enResult.matches || []).filter(isDetectionIssue) : null;

  // If one call failed entirely, the other language wins by default.
  if (!esMatches) return {lang: 'en', result: enResult};
  if (!enMatches) return {lang: 'es', result: esResult};

  var esCount = esMatches.length;
  var enCount = enMatches.length;

  // LT es accepts it; LT en flags it → Spanish.
  if (esCount === 0 && enCount > 0) return {lang: 'es', result: esResult};

  // LT en accepts it; LT es flags it. Two possibilities:
  //   (a) English word that LT en knows is valid.
  //   (b) Spanish word with an accent error (e.g. "caida"→"caída").
  // Discriminate by edit distance: accent fixes are always edit distance ≤ 1.
  // If LT es's correction is close (d ≤ 1), it's a Spanish accent error.
  // If LT es's correction is far (or filtered out by the length guard), it's English.
  if (enCount === 0 && esCount > 0) {
    var esFirst = firstCorrectedText(text, esResult); // uses isSpellingIssue (length-guarded)
    if (esFirst && editDistance(text, esFirst) <= 1) return {lang: 'es', result: esResult};
    return {lang: 'en', result: enResult};
  }

  // Both endpoints accept the word — default to Spanish. This sheet is
  // Spanish-focused; words valid in both languages ("no", "si") are more
  // likely to be Spanish vocabulary entries than English ones.
  if (esCount === 0 && enCount === 0) return {lang: 'es', result: esResult};

  // Both flag the word — pick the language whose correction is closest to the original.
  var chosen = closerResult(text, esResult, enResult);
  // closerResult returns null when both results have detection matches but neither has
  // spelling-issue matches (all suggestions shorten the span). Fall back to Spanish default.
  if (!chosen) return {lang: 'es', result: esResult};
  return {lang: chosen === esResult ? 'es' : 'en', result: chosen};
}

/**
 * One-time backfill: writes the GOOGLETRANSLATE formula to column B for all
 * rows where column A is non-empty and column B is currently empty.
 * Run once from Extensions > Apps Script after deploying the updated GAS.
 *
 * Assumes row 1 is a header row and data begins at row 2. If your sheet has
 * no header row, update the start row before running.
 */
function setupTranslationFormulas() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  var data = sheet.getRange(2, COL_VOCAB, lastRow - 1, COL_TRANSLATION).getValues();
  for (var i = 0; i < data.length; i++) {
    var row = i + 2;
    if (data[i][0] !== '' && data[i][1] === '') {
      sheet.getRange(row, COL_TRANSLATION).setFormula(translateFormula(row));
    }
  }
}
