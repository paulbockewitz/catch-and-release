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

  // Determine what language auto-detect returned.
  var detectedCode = (result.language &&
                      result.language.detectedLanguage &&
                      result.language.detectedLanguage.code) || '';
  var confidence = (result.language &&
                    result.language.detectedLanguage &&
                    result.language.detectedLanguage.confidence) || 0;

  var isExpected = detectedCode.startsWith('es') || detectedCode.startsWith('en');

  if (!isExpected || confidence < 0.5) {
    // Auto-detect landed on a wrong language (e.g. Italian for "ultimamente")
    // or was too uncertain. Retry with explicit Spanish so detection plays no
    // role — the Spanish checker finds missing accents directly.
    var retry = callLanguageTool(originalText, 'es');
    if (retry) result = retry;
  }

  // Accept spelling errors and typographical errors (accent placement).
  // "misspelling"  = wrong letters: covencion, caida (changes word meaning).
  // "typographical" = accent only: ultimamente → últimamente.
  // Grammar, style, and punctuation are excluded; the PUNCTUATION and
  // TYPOGRAPHY categories are also disabled at the API level.
  var spellingMatches = (result.matches || []).filter(function(m) {
    return m.rule &&
           (m.rule.issueType === 'misspelling' || m.rule.issueType === 'typographical') &&
           m.replacements &&
           m.replacements.length > 0;
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
