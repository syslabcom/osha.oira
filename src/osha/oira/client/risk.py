from Acquisition import aq_inner
from Products.statusmessages.interfaces import IStatusMessage
from euphorie.client import model
from euphorie.client import risk
from euphorie.client.navigation import FindNextQuestion
from euphorie.client.navigation import FindPreviousQuestion
from euphorie.client.navigation import QuestionURL
from euphorie.client.navigation import getTreeData
from euphorie.client.session import SessionManager
from euphorie.client.update import redirectOnSurveyUpdate
from euphorie.client.utils import HasText
from euphorie.content.solution import ISolution
from euphorie.content.utils import StripMarkup
from five import grok
from osha.oira import _
from z3c.saconfig import Session
from zope.component import getMultiAdapter
from zope.i18n import translate
from .interfaces import IOSHAIdentificationPhaseSkinLayer
from .interfaces import IOSHAActionPlanPhaseSkinLayer

grok.templatedir("templates")

IMAGE_CLASS = {
    0: '',
    1: 'twelve',
    2: 'six',
    3: 'four',
    4: 'three',
}

DESCRIPTION_CROP_LENGTH = 200


class OSHAIdentificationView(risk.EvaluationView):
    """ This view is a combination of the Euphorie Identification and Evauation
        views.
        The risk is both identified and evaluated in this step.
    """
    grok.layer(IOSHAIdentificationPhaseSkinLayer)
    grok.template("risk_identification")
    question_filter = None

    def update(self):
        if redirectOnSurveyUpdate(self.request):
            return

        self.risk = self.request.survey.restrictedTraverse(
            self.context.zodb_path.split("/"))

        if self.request.environ["REQUEST_METHOD"] == "POST":
            reply = self.request.form
            answer = reply.get("answer")
            self.context.comment = reply.get("comment")
            self.context.postponed = (answer == "postponed")
            if self.context.postponed:
                self.context.identification = None
            else:
                self.context.identification = answer
                if self.risk.type in ('top5', 'policy'):
                    self.context.priority = 'high'
                elif self.risk.evaluation_method == 'calculated':
                    self.calculatePriority(self.risk, reply)
                elif self.risk.evaluation_method == "direct":
                    self.context.priority = reply.get("priority")

            SessionManager.session.touch()

            if reply["next"] == "previous":
                next = FindPreviousQuestion(
                    self.context,
                    filter=self.question_filter)
                if next is None:
                    # We ran out of questions, step back to intro page
                    url = "%s/identification" % \
                        self.request.survey.absolute_url()
                    self.request.response.redirect(url)
                    return
            else:
                next = FindNextQuestion(
                    self.context,
                    filter=self.question_filter)
                if next is None:
                    # We ran out of questions, proceed to the action plan
                    url = "%s/actionplan" % self.request.survey.absolute_url()
                    self.request.response.redirect(url)
                    return

            url = QuestionURL(self.request.survey, next, phase="identification")
            self.request.response.redirect(url)
        else:
            self.tree = getTreeData(self.request, self.context)
            self.title = self.context.parent.title
            self.show_info = self.risk.image or \
                HasText(self.risk.description) or \
                HasText(self.risk.legal_reference)
            number_images = getattr(self.risk, 'image', None) and 1 or 0
            if number_images:
                for i in range(2, 5):
                    number_images += getattr(
                        self.risk, 'image{0}'.format(i), None) and 1 or 0
            self.has_images = number_images > 0
            self.number_images = number_images
            self.image_class = IMAGE_CLASS[number_images]
            number_files = 0
            for i in range(1, 5):
                number_files += getattr(
                    self.risk, 'file{0}'.format(i), None) and 1 or 0
            self.has_files = number_files > 0
            self.risk_number = self.context.number

            ploneview = getMultiAdapter(
                (self.context, self.request), name="plone")
            stripped_description = StripMarkup(self.risk.description)
            if len(stripped_description) > DESCRIPTION_CROP_LENGTH:
                self.description_intro = ploneview.cropText(
                    stripped_description, DESCRIPTION_CROP_LENGTH)
            else:
                self.description_intro = ""
            self.description_probability = _(
                u"help_default_probability", default=u"Indicate how "
                "likely occurence of this risk is in a normal situation.")
            self.description_frequency = _(
                u"help_default_frequency", default=u"Indicate how often this "
                u"risk occurs in a normal situation.")
            self.description_severity = _(
                u"help_default_severity", default=u"Indicate the "
                "severity if this risk occurs.")
            if getattr(self.request.survey, 'enable_custom_evaluation_descriptions', False):
                if self.request.survey.evaluation_algorithm != 'french':
                    custom_dp = getattr(
                        self.request.survey, 'description_probability', '') or ''
                    self.description_probability = custom_dp.strip() or self.description_probability
                custom_df = getattr(self.request.survey, 'description_frequency', '') or ''
                self.description_frequency = custom_df.strip() or self.description_frequency
                custom_ds = getattr(self.request.survey, 'description_severity', '') or ''
                self.description_severity = custom_ds.strip() or self.description_severity

            super(risk.EvaluationView, self).update()


class OSHAActionPlanView(risk.ActionPlanView):
    grok.layer(IOSHAActionPlanPhaseSkinLayer)
    grok.template("risk_actionplan")

    @property
    def is_custom_risk(self):
        return getattr(self.context, 'is_custom_risk', False)

    def update(self):
        if redirectOnSurveyUpdate(self.request):
            return
        context = aq_inner(self.context)

        self.next_is_report = False
        # already compute "next" here, so that we can know in the template
        # if the next step might be the report phase, in which case we
        # need to switch off the sidebar
        next = FindNextQuestion(
            context, filter=self.question_filter)
        if next is None:
            # We ran out of questions, proceed to the report
            url = "%s/report" % self.request.survey.absolute_url()
            self.next_is_report = True
        else:
            url = QuestionURL(
                self.request.survey, next, phase="actionplan")

        if self.request.environ["REQUEST_METHOD"] == "POST":
            reply = self.request.form
            session = Session()
            context.comment = reply.get("comment")
            context.priority = reply.get("priority")

            new_plans = self.extract_plans_from_request()
            for plan in context.action_plans:
                session.delete(plan)
            context.action_plans.extend(new_plans)
            SessionManager.session.touch()

            if reply["next"] == "previous":
                next = FindPreviousQuestion(
                    context, filter=self.question_filter)
                if next is None:
                    # We ran out of questions, step back to intro page
                    url = "%s/evaluation" \
                            % self.request.survey.absolute_url()
                else:
                    url = QuestionURL(
                        self.request.survey, next, phase="actionplan")
            return self.request.response.redirect(url)

        else:
            self.data = context
            if len(context.action_plans) == 0:
                self.data.empty_action_plan = [model.ActionPlan()]

        self.title = context.parent.title
        self.tree = getTreeData(
                self.request, context,
                filter=self.question_filter, phase="actionplan")
        if self.context.is_custom_risk:
            self.risk = self.context
            self.description_intro = u""
            self.risk.description = u""
            number_images = 0
        else:
            self.risk = self.request.survey.restrictedTraverse(
                context.zodb_path.split("/"))
            number_images = getattr(self.risk, 'image', None) and 1 or 0
            if number_images:
                for i in range(2, 5):
                    number_images += getattr(
                        self.risk, 'image{0}'.format(i), None) and 1 or 0
            ploneview = getMultiAdapter(
                (self.context, self.request), name="plone")
            stripped_description = StripMarkup(self.risk.description)
            if len(stripped_description) > DESCRIPTION_CROP_LENGTH:
                self.description_intro = ploneview.cropText(
                    stripped_description, DESCRIPTION_CROP_LENGTH)
            else:
                self.description_intro = ""
            self.solutions = [solution for solution in self.risk.values()
                            if ISolution.providedBy(solution)]

        self.number_images = number_images
        self.has_images = number_images > 0
        self.image_class = IMAGE_CLASS[number_images]
        self.risk_number = self.context.number
        lang = getattr(self.request, 'LANGUAGE', 'en')
        if "-" in lang:
            elems = lang.split("-")
            lang = "{0}_{1}".format(elems[0], elems[1].upper())
        self.delete_confirmation = translate(_(
            u"Are you sure you want to delete this measure? This action can "
            u"not be reverted."),
            target_language=lang)
        self.override_confirmation = translate(_(
            u"The current text in the fields 'Action plan', 'Prevention plan' and "
            u"'Requirements' of this measure will be overwritten. This action cannot be "
            u"reverted. Are you sure you want to continue?"),
            target_language=lang)
        self.message_date_before = translate(_(
            u"error_validation_before_end_date",
            default=u"This date must be on or before the end date."),
            target_language=lang)
        self.message_date_after = translate(_(
            u"error_validation_after_start_date",
            default=u"This date must be on or after the start date."),
            target_language=lang)
        self.message_positive_number = translate(_(
            u"error_validation_positive_whole_number",
            default=u"This value must be a positive whole number."),
            target_language=lang)
        super(risk.ActionPlanView, self).update()

    def extract_plans_from_request(self):
        """ Create new ActionPlan objects by parsing the Request.
        """
        new_plans = []
        added = 0
        updated = 0
        existing_plans = {}
        for plan in self.context.action_plans:
            existing_plans[str(plan.id)] = plan
        form = self.request.form
        form["action_plans"] = []
        for i in range(0, len(form['measure'])):
            measure = dict([p for p in form['measure'][i].items()
                            if p[1].strip()])
            form['action_plans'].append(measure)
            if len(measure):
                budget = measure.get("budget")
                budget = budget and budget.split(',')[0].split('.')[0]
                if measure.get('id', '-1') in existing_plans:
                    plan = existing_plans[measure.get('id')]
                    if (
                        measure.get("action_plan") != plan.action_plan or
                        measure.get("prevention_plan") != plan.prevention_plan or
                        measure.get("requirements") != plan.requirements or
                        measure.get("responsible") != plan .responsible or (
                            plan.budget and (budget != str(plan.budget))
                            or plan.budget is None and budget
                        ) or (
                            (plan.planning_start and
                                measure.get('planning_start') != plan.planning_start.strftime('%Y-%m-%d'))
                            or (plan.planning_start is None and measure.get('planning_start'))
                        ) or (
                            (plan.planning_end and
                                measure.get('planning_end') != plan.planning_end.strftime('%Y-%m-%d'))
                            or (plan.planning_end is None and measure.get('planning_end'))
                        )
                    ):
                        updated += 1
                    del existing_plans[measure.get('id')]
                else:
                    added += 1
                new_plans.append(
                    model.ActionPlan(
                        action_plan=measure.get("action_plan"),
                        prevention_plan=measure.get("prevention_plan"),
                        requirements=measure.get("requirements"),
                        responsible=measure.get("responsible"),
                        budget=budget,
                        planning_start=measure.get('planning_start'),
                        planning_end=measure.get('planning_end')
                    )
                )
        removed = len(existing_plans)
        if added == 0 and updated == 0 and removed == 0:
            IStatusMessage(self.request).add(
                _(u"No changes were made to measures in your action plan."),
                type='info'
            )
        if added == 1:
            IStatusMessage(self.request).add(
                _(u"message_measure_saved", default=u"A measure has been added to your action plan."),
                type='success'
            )
        elif added == 2:
            IStatusMessage(self.request).add(
                _(
                    u"message_measures_saved_2",
                    default=u"${no_of_measures} measures have been added to your action plan.",
                    mapping={'no_of_measures': str(added)}),
                type='success'
            )
        elif added in (3, 4):
            IStatusMessage(self.request).add(
                _(
                    u"message_measures_saved_3_4",
                    default=u"${no_of_measures} measures have been added to your action plan.",
                    mapping={'no_of_measures': str(added)}),
                type='success'
            )
        elif added > 4:
            IStatusMessage(self.request).add(
                _(
                    u"message_measures_saved",
                    default=u"${no_of_measures} measures have been added to your action plan.",
                    mapping={'no_of_measures': str(added)}),
                type='success'
            )

        if updated == 1:
            IStatusMessage(self.request).add(
                _(u"message_measure_updated", default=u"A measure has been updated in your action plan."),
                type='success'
            )
        elif updated == 2:
            IStatusMessage(self.request).add(
                _(
                    u"message_measures_updated_2",
                    default=u"${no_of_measures} measures have been updated in your action plan.",
                    mapping={'no_of_measures': str(updated)}),
                type='success'
            )
        elif updated in (3, 4):
            IStatusMessage(self.request).add(
                _(
                    u"message_measures_updated_3_4",
                    default=u"${no_of_measures} measures have been updated in your action plan.",
                    mapping={'no_of_measures': str(updated)}),
                type='success'
            )
        elif updated > 4:
            IStatusMessage(self.request).add(
                _(
                    u"message_measures_updated",
                    default=u"${no_of_measures} measures have been updated in your action plan.",
                    mapping={'no_of_measures': str(updated)}),
                type='success'
            )

        if removed == 1:
            IStatusMessage(self.request).add(
                _(u"message_measure_removed", default=u"A measure has been removed from your action plan."),
                type='success'
            )
        elif removed == 2:
            IStatusMessage(self.request).add(
                _(
                    u"message_measures_removed_3",
                    default=u"${no_of_measures} measures have been removed from your action plan.",
                    mapping={'no_of_measures': str(removed)}),
                type='success'
            )
        elif removed in (3, 4):
            IStatusMessage(self.request).add(
                _(
                    u"message_measures_removed_3_4",
                    default=u"${no_of_measures} measures have been removed from your action plan.",
                    mapping={'no_of_measures': str(removed)}),
                type='success'
            )
        elif removed > 4:
            IStatusMessage(self.request).add(
                _(
                    u"message_measures_removed",
                    default=u"${no_of_measures} measures have been removed from your action plan.",
                    mapping={'no_of_measures': str(removed)}),
                type='success'
            )
        return new_plans
