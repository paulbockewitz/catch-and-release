// Vocab Sheet Spell-Check — Google Apps Script
//
// Registers an installable onEdit trigger that calls the LanguageTool free
// REST API on every column A edit. Corrects spelling errors (including missing
// accents) in-place and records the original value as a cell note.
//
// SETUP: Run createTrigger() once from Extensions > Apps Script to register
// the installable trigger. Simple onEdit cannot call UrlFetchApp — the
// installable trigger is required.

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
  if (range.getColumn() !== 1) return;

  // For single-cell edits, use the edited range.
  // For bulk pastes (numRows > 1), correct only the first row.
  var cell;
  if (range.getNumRows() === 1) {
    cell = range;
  } else {
    cell = range.getSheet().getRange(range.getRow(), 1);
  }

  var originalText = cell.getValue();
  if (typeof originalText !== 'string' || originalText.trim() === '') return;

  var row = cell.getRow();
  var sheet = cell.getSheet();
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

  // Write detected language to column C (1-based column 3).
  sheet.getRange(row, 3).setValue(detectedLang);

  // Write GOOGLETRANSLATE formula to column B if currently empty.
  // This write happens unconditionally (before the spelling-correction check)
  // so that correctly-spelled words (spellingMatches.length === 0) also get
  // their translation formula — not just words that needed correction.
  var bCell = sheet.getRange(row, 2);
  if (bCell.getValue() === '') {
    bCell.setFormula(
      '=IF(A' + row + '="","",IFERROR(GOOGLETRANSLATE(A' + row + ',C' + row + ',IF(C' + row + '="es","en","es")),"))'
    );
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
    cell.setNote(originalText);
    cell.setValue(correctedText);
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
    if (response.getResponseCode() !== 200) return null;
    return JSON.parse(response.getContentText());
  } catch (err) {
    return null;
  }
}

/**
 * Returns true for matches that represent a genuine spelling or accent error
 * AND whose replacement is at least as long as the original span. The length
 * guard prevents applying shortening corrections (e.g. "lucido"→"lucid").
 * Used by spellingMatches and firstCorrectedText — both must stay in sync.
 * detectLanguage uses a broader filter (isDetectionIssue, defined inline)
 * so that short-replacement foreign-word flags still count toward detection.
 */
function isSpellingIssue(m) {
  return m.rule &&
    (m.rule.issueType === 'misspelling' || m.rule.issueType === 'typographical') &&
    m.replacements && m.replacements.length > 0 &&
    m.replacements[0].value.length >= m.length;
}

/**
 * Determine language from LanguageTool results.
 *
 * Detection uses a broader filter than correction: any misspelling/typographical
 * flag counts regardless of replacement length. This is necessary because LT may
 * suggest shorter replacements for foreign words (e.g. "however"→"hoy" in LT es),
 * which the correction filter would exclude but which still signal "wrong language."
 *
 * @param {string} text - Original text (used for tiebreaker)
 * @param {Object|null} esResult - LT response for 'es'
 * @param {Object|null} enResult - LT response for 'en-US'
 * @returns {{lang: string, result: Object}} Detected language and result to use for correction
 */
function detectLanguage(text, esResult, enResult) {
  function isDetectionIssue(m) {
    return m.rule &&
      (m.rule.issueType === 'misspelling' || m.rule.issueType === 'typographical') &&
      m.replacements && m.replacements.length > 0;
  }

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

  if (esCount === 0 && enCount === 0) return {lang: 'es', result: esResult}; // R5 tiebreaker

  // Both flag the word — pick the language whose correction is closest to the original.
  var chosen = closerResult(text, esResult, enResult);
  return {lang: chosen === esResult ? 'es' : 'en', result: chosen || esResult};
}

/**
 * One-time backfill: writes the GOOGLETRANSLATE formula to column B for all
 * rows where column A is non-empty and column B is currently empty.
 * Run once from Extensions > Apps Script after deploying the updated GAS.
 */
function setupTranslationFormulas() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  var data = sheet.getRange(2, 1, lastRow - 1, 2).getValues();
  for (var i = 0; i < data.length; i++) {
    var row = i + 2;
    if (data[i][0] !== '' && data[i][1] === '') {
      sheet.getRange(row, 2).setFormula(
        '=IF(A' + row + '="","",IFERROR(GOOGLETRANSLATE(A' + row + ',C' + row + ',IF(C' + row + '="es","en","es")),"))'
      );
    }
  }
}
