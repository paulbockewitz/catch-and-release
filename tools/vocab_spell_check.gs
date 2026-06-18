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

  var result = callLanguageTool(originalText);
  if (!result) return;

  // When language was auto-detected, require confidence >= 0.5.
  // Single short words are prone to misidentification; a low-confidence
  // response is more likely to produce wrong corrections than right ones.
  var detectedLang = result.language && result.language.detectedLanguage;
  if (detectedLang && typeof detectedLang.confidence === 'number' &&
      detectedLang.confidence < 0.5) {
    cell.setNote('LT: low confidence');
    return;
  }

  // Keep only spelling matches that have at least one replacement suggestion.
  // Grammar, style, and punctuation matches are intentionally ignored.
  var spellingMatches = (result.matches || []).filter(function(m) {
    return m.rule &&
           m.rule.issueType === 'misspelling' &&
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

  if (correctedText !== originalText) {
    cell.setNote(originalText);
    cell.setValue(correctedText);
  }
}

/**
 * POST to the LanguageTool free REST API.
 *
 * @param {string} text - Text to check
 * @returns {Object|null} Parsed JSON response, or null on any error
 */
function callLanguageTool(text) {
  var options = {
    method: 'post',
    payload: {
      text: text,
      language: 'auto',
      preferredVariants: 'es-ES,en-US',
      disabledCategories: 'PUNCTUATION,TYPOGRAPHY'
    },
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
