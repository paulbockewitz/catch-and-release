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

  var result = callLanguageTool(originalText, 'auto');
  if (!result) return;

  var detectedCode = (result.language &&
                      result.language.detectedLanguage &&
                      result.language.detectedLanguage.code) || '';
  var confidence = (result.language &&
                    result.language.detectedLanguage &&
                    result.language.detectedLanguage.confidence) || 0;
  var isExpected = detectedCode.startsWith('es') || detectedCode.startsWith('en');

  // When detected as English, also check Spanish — English may truncate a Spanish word
  // (e.g. "lucido" → "lucid") when the correct fix is just an accent ("lúcido").
  // If Spanish has an equal-or-closer correction, prefer it.
  if (isExpected && detectedCode.startsWith('en')) {
    var enFirst = firstCorrectedText(originalText, result);
    if (enFirst) {
      var esCheck = callLanguageTool(originalText, 'es');
      var esFirst = firstCorrectedText(originalText, esCheck);
      if (esFirst && editDistance(originalText, esFirst) <= editDistance(originalText, enFirst)) {
        result = esCheck;
      }
    }
  }

  if (!isExpected || confidence < 0.5) {
    // Auto-detect was unreliable (wrong language or too uncertain).
    // Try both Spanish and English explicitly, then apply whichever correction
    // is closer to the original — edit distance breaks the ambiguity.
    // Example: "distrubute" → es gives "distribuye" (d=2), en gives "distribute" (d=1) → en wins.
    // Example: "ultimamente" → es gives "últimamente" (d=1), en gives nothing → es wins.
    // If neither finds corrections, the word is already correct in its own language —
    // do not apply the unreliable detector's suggestions (e.g. Czech "imbalance" → "invádanse").
    var esResult = callLanguageTool(originalText, 'es');
    var enResult = callLanguageTool(originalText, 'en-US');
    var esFirst = firstCorrectedText(originalText, esResult);
    var enFirst = firstCorrectedText(originalText, enResult);
    if (!enFirst) {
      // English has no correction. Could be valid English (bail) or a Spanish word
      // with only an accent error (apply). Accent fixes are edit distance ≤ 1;
      // false-positive Spanish "corrections" of English words are much farther away.
      // e.g. "imbalance" → "invádanse" (d≈8) should bail; "ultimamente" → "últimamente" (d=1) should apply.
      if (!esFirst || editDistance(originalText, esFirst) > 1) return;
      result = esResult;
    } else {
      var chosen = closerResult(originalText, esResult, enResult);
      if (chosen) {
        result = chosen;
      } else {
        return;
      }
    }
  }

  // Accept spelling errors and typographical errors (accent placement).
  // "misspelling"   = wrong letters: covencion, caida (changes word meaning).
  // "typographical" = accent only:   ultimamente → últimamente.
  // Grammar, style, and punctuation are excluded; the PUNCTUATION and
  // TYPOGRAPHY categories are also disabled at the API level.
  var spellingMatches = (result.matches || []).filter(function(m) {
    if (!m.rule) return false;
    if (m.rule.issueType !== 'misspelling' && m.rule.issueType !== 'typographical') return false;
    if (!m.replacements || m.replacements.length === 0) return false;
    // Skip corrections that shorten the matched span — accent fixes are always the same
    // length, and shrinking corrections (e.g. "lucido" → "lucid") are usually English
    // misidentifying a Spanish word by dropping its final vowel.
    if (m.replacements[0].value.length < m.length) return false;
    return true;
  });

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
  var matches = (result.matches || []).filter(function(m) {
    return m.rule &&
           (m.rule.issueType === 'misspelling' || m.rule.issueType === 'typographical') &&
           m.replacements && m.replacements.length > 0 &&
           m.replacements[0].value.length >= m.length;
  });
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
 * @param {string} language - Language code ('auto', 'es', 'en-US', etc.)
 * @returns {Object|null} Parsed JSON response, or null on any error
 */
function callLanguageTool(text, language) {
  var payload = {
    text: text,
    language: language,
    disabledCategories: 'PUNCTUATION,TYPOGRAPHY'
  };
  if (language === 'auto') {
    payload.preferredVariants = 'es-ES,en-US';
  }

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
