annotation = ($filter) ->
  link: (scope, iElement, iAttrs, controller) ->
    annotation = scope.annotation
    thread = scope.threads.getSpecificChild annotation.id
    angular.extend scope, annotation
    angular.extend scope,
      collapsed: false
      created: ($filter 'fuzzyTime') annotation.created
      user: ($filter 'userName') annotation.user
      replies: (c.message.annotation for c in (thread?.children or []))
      replyCount: thread?.flattenChildren()?.length or 0
    scope.$watch 'editable', (newValue) =>
      if newValue
        scope.text = scope.annotation.text
        iElement.find('textarea').focus()
      else
        scope.text = ($filter 'converter') scope.annotation.text
  restrict: 'C'
  scope: true
annotation.$inject = ['$filter']


tabReveal = ($parse) ->
  compile: (tElement, tAttrs, transclude) ->
    panes = []

    pre: (scope, iElement, iAttrs, [ngModel, tabbable] = controller) ->
      # Hijack the tabbable controller's addPane so that the visibility of the
      # secret ones can be managed. This avoids traversing the DOM to find
      # the tab panes.
      addPane = tabbable.addPane
      tabbable.addPane = (element, attr) =>
        removePane = addPane.call tabbable, element, attr
        panes.push
          element: element
          attr: attr
        =>
          for i in [0..panes.length]
            if panes[i].element is element
              panes.splice i, 1
              break
          removePane()

    post: (scope, iElement, iAttrs, [ngModel, tabbable] = controller) ->
      tabs = angular.element(iElement.children()[0]).find('li')
      hiddenPanes = ($parse iAttrs.tabReveal)()
      unless angular.isArray hiddenPanes
        throw (new TypeError 'tabReveal expression must evaluate to an Array')

      update = =>
        for i in [0..panes.length-1]
          pane = panes[i]
          value = pane.attr.value || pane.attr.title
          if value == ngModel.$modelValue
            deform.focusFirstInput pane.element
            pane.element.css 'display', ''
            angular.element(tabs[i]).css 'display', ''
          else if value in hiddenPanes
            pane.element.css 'display', 'none'
            angular.element(tabs[i]).css 'display', 'none'

      scope.$watch iAttrs.ngModel, => scope.$evalAsync update
  require: ['ngModel', 'tabbable']
tabReveal.$inject = ['$parse']


angular.module('h.directives', ['ngSanitize', 'deform'])
  .directive('annotation', annotation)
  .directive('tabReveal', tabReveal)
