/**
 * Greenway Centre — Operational Discovery Form
 *
 * Purpose: Open-minded discovery about how the team tracks and manages work.
 * No mention of email, InboxIQ, or any product.
 * Validates the "ticket as unit of work" direction.
 *
 * How to use:
 * 1. Go to https://script.google.com
 * 2. Create new project, name it "Greenway Discovery Form"
 * 3. Paste this file, run createGreenwayDiscoveryForm
 * 4. Copy the share link from Execution log
 */

function createGreenwayDiscoveryForm() {
  const form = FormApp.create('How your team manages incoming requests — a short survey');

  form.setDescription(
    'We are researching how small teams and charities manage day-to-day requests and communications. ' +
    'This is a discovery survey — there are no right or wrong answers. ' +
    'Your responses are confidential and will not be used for sales purposes.'
  );

  form.setCollectEmail(false);
  form.setProgressBar(true);

  // ── Section 1: How work arrives ──────────────────────────────────────────

  form.addSectionHeaderItem()
    .setTitle('Section 1 — How requests arrive')
    .setHelpText('Help us understand where your team\'s work comes from.');

  form.addCheckboxItem()
    .setTitle('How do requests or enquiries arrive at your organisation?')
    .setHelpText('Select all that apply.')
    .setChoiceValues([
      'Email',
      'Phone calls',
      'Walk-ins or in person',
      'Online forms or website',
      'Social media messages',
      'Referrals from other organisations',
      'Internal requests from colleagues',
      'Other'
    ])
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('Which type of request takes up the most of your team\'s time?')
    .setHelpText('Think about volume and the effort each one requires.')
    .setRequired(true);

  // ── Section 2: How work is tracked ───────────────────────────────────────

  form.addSectionHeaderItem()
    .setTitle('Section 2 — How your team tracks work')
    .setHelpText('We want to understand what happens between a request arriving and it being resolved.');

  form.addParagraphTextItem()
    .setTitle('When a request arrives, how does your team decide who handles it?')
    .setHelpText('Walk us through what actually happens — even if it\'s informal.')
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How does your team currently keep track of open requests?')
    .setChoiceValues([
      'We don\'t — things get handled as they come in',
      'Informally — team members remember what they\'re working on',
      'A shared spreadsheet or document',
      'A task management tool (Trello, Asana, Monday, etc.)',
      'A ticketing system (Zendesk, Freshdesk, etc.)',
      'Email folders or labels',
      'Something else'
    ])
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('Has a request ever fallen through the cracks — not handled, responded to too late, or lost?')
    .setHelpText('Describe what happened if you can. What was the impact?')
    .setRequired(false);

  // ── Section 3: How decisions are made ────────────────────────────────────

  form.addSectionHeaderItem()
    .setTitle('Section 3 — Decisions and approvals')
    .setHelpText('We want to understand how your team makes decisions on requests.');

  form.addParagraphTextItem()
    .setTitle('Are there requests that require approval or sign-off before your team can respond?')
    .setHelpText('For example: financial requests, sensitive communications, commitments on behalf of the organisation.')
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('When a request needs approval, what usually happens?')
    .setChoiceValues([
      'We handle it directly — no approval needed',
      'We ask a manager verbally or in person',
      'We forward the email or message to someone',
      'We use a formal approval process',
      'It varies depending on the type of request'
    ])
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('What happens when the right person is unavailable to handle a request?')
    .setHelpText('Does it wait, get reassigned, or something else?')
    .setRequired(false);

  // ── Section 4: The cost of the current approach ───────────────────────────

  form.addSectionHeaderItem()
    .setTitle('Section 4 — What is not working')
    .setHelpText('Honest answers here are the most useful.');

  form.addParagraphTextItem()
    .setTitle('What is the biggest operational challenge your team faces day to day?')
    .setHelpText('Not the biggest strategic challenge — the day-to-day friction.')
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How often do things get missed, delayed, or handled twice because of how work is tracked?')
    .setChoiceValues([
      'Daily',
      'A few times a week',
      'Once a week',
      'Rarely',
      'Never — our current system works well'
    ])
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('If you could fix one thing about how your team manages incoming requests, what would it be?')
    .setHelpText('Be as specific as you can — this is the most important question.')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('Are there requests your team handles the same way every time?')
    .setHelpText('For example: a type of enquiry that always goes to the same person, always needs the same information, or always follows the same steps. Describe one if you can.')
    .setRequired(false);

  // ── Section 5: Open door ──────────────────────────────────────────────────

  form.addSectionHeaderItem()
    .setTitle('Section 5 — One last thing');

  form.addMultipleChoiceItem()
    .setTitle('Would you be open to a 20-minute conversation to go deeper on any of this?')
    .setChoiceValues([
      'Yes — happy to talk',
      'Maybe — send me more details first',
      'No thanks'
    ])
    .setRequired(true);

  form.setConfirmationMessage(
    'Thank you — this is genuinely useful. ' +
    'If you said yes to a conversation, we will be in touch within a few days.'
  );

  const url = form.getPublishedUrl();
  Logger.log('Form created successfully.');
  Logger.log('Share this link: ' + url);
  Logger.log('Edit at: ' + form.getEditUrl());
}
