function createDiscoveryForm() {
  const form = FormApp.create('Discovery Interview — Operational Problems & Decision-Making');

  form.setDescription(
    'This is a discovery interview, not a sales process. ' +
    'We are researching the operational problems teams face when making decisions, coordinating work, and responding to issues. ' +
    'Your answers are confidential and will only be used to understand the problem space. ' +
    'There are no right or wrong answers — honest responses are the most valuable.'
  );

  form.setCollectEmail(false);
  form.setProgressBar(true);

  form.addSectionHeaderItem()
    .setTitle('Section 1 — Current State')
    .setHelpText('Help us understand your role and what you need to do your job well.');

  form.addParagraphTextItem()
    .setTitle('What is your role?')
    .setHelpText('Your title, team, and what you are accountable for day-to-day.')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('What decisions are you responsible for?')
    .setHelpText('Think about recurring decisions — daily, weekly, or monthly.')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('What information do you need to make those decisions?')
    .setHelpText('Where does that information come from? How do you get it?')
    .setRequired(true);

  form.addSectionHeaderItem()
    .setTitle('Section 2 — Problems and Friction')
    .setHelpText('Tell us about what makes your job harder than it needs to be.');

  form.addParagraphTextItem()
    .setTitle('What is the most frustrating part of your job?')
    .setHelpText('Not necessarily technology — could be process, people, or systems.')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('Think about the last time work was delayed or a decision was difficult. What happened?')
    .setHelpText('Describe a real recent example, not a general problem.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('Where did you have to look, ask, or check to resolve the issue?')
    .setHelpText('For example: email, spreadsheets, meetings, databases, CRM, EHR, SharePoint, Teams, paper notes, or colleagues.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('What usually causes delays, missed actions, or confusion in your work?')
    .setHelpText('What slows you down most — waiting, searching, chasing, unclear ownership, or something else?')
    .setRequired(false);

  form.addSectionHeaderItem()
    .setTitle('Section 3 — Consequences')
    .setHelpText('Help us understand what is at stake when things go wrong.');

  form.addParagraphTextItem()
    .setTitle('What happens when important information, decisions, or actions are missed?')
    .setHelpText('Describe a real example if you can — what broke, what had to be fixed.')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('Who is affected when this happens?')
    .setHelpText('For example: customers, patients, managers, compliance teams, finance, operations, suppliers, or frontline staff.')
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('How often does that happen?')
    .setChoiceValues([
      'Daily',
      'A few times a week',
      'Once a week',
      'A few times a month',
      'Rarely'
    ])
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('What is the impact when it happens?')
    .setHelpText('Time lost, money, risk, compliance exposure, customer/patient impact, reputation, stress, or rework.')
    .setRequired(false);

  form.addSectionHeaderItem()
    .setTitle('Section 4 — Existing Solutions')
    .setHelpText('Tell us what you already use and what you think of it.');

  form.addParagraphTextItem()
    .setTitle('How do you solve this problem today?')
    .setHelpText('Walk us through what you actually do — even if it is a workaround.')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('Walk me through the steps you take today.')
    .setHelpText('Start from when the problem appears to when it is resolved.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('What tools do you use?')
    .setHelpText('Software, spreadsheets, physical processes — list everything relevant.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('What do you dislike about your current tools or process?')
    .setHelpText('What would you change first if you could?')
    .setRequired(false);

  form.addSectionHeaderItem()
    .setTitle('Section 5 — Priority')
    .setHelpText('Last questions — about what matters most.');

  form.addParagraphTextItem()
    .setTitle('If you could fix one operational problem this year, what would it be?')
    .setHelpText('Not the most urgent fire — the one that, if solved, would change how you work.')
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How important is solving this problem in the next 12 months?')
    .setChoiceValues([
      'Critical — we urgently need to solve it',
      'High — it is a serious problem',
      'Medium — useful but not urgent',
      'Low — annoying but manageable',
      'Not sure'
    ])
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('Would you be open to a 20–30 minute follow-up conversation?')
    .setChoiceValues([
      'Yes',
      'Maybe',
      'No'
    ])
    .setRequired(false);

  form.addTextItem()
    .setTitle('If yes, what is the best email address to contact you?')
    .setRequired(false);

  form.setConfirmationMessage(
    'Thank you. Your responses are genuinely useful. ' +
    'We will reach out if you agreed to a follow-up conversation.'
  );

  const url = form.getPublishedUrl();
  Logger.log('Form created successfully.');
  Logger.log('Share this link: ' + url);
  Logger.log('Edit the form at: ' + form.getEditUrl());
}
