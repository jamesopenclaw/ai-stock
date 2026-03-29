import { config } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const passthrough = (tag = 'div', extra = {}) =>
  defineComponent({
    inheritAttrs: false,
    props: {
      modelValue: {
        type: [String, Number, Boolean, Array, Object],
        default: undefined
      },
      description: {
        type: String,
        default: ''
      }
    },
    setup(props, { slots, attrs }) {
      return () =>
        h(
          tag,
          { ...attrs, ...extra },
          [
            props.description ? h('span', { class: 'stub-description' }, props.description) : null,
            slots.header?.(),
            slots.label?.(),
            slots.default?.(),
          ]
        )
    }
  })

const emptyStub = (tag = 'div', extra = {}) =>
  defineComponent({
    inheritAttrs: false,
    setup(_props, { attrs }) {
      return () => h(tag, { ...attrs, ...extra })
    }
  })

config.global.components = {
  ElContainer: passthrough('div'),
  ElAside: passthrough('aside'),
  ElHeader: passthrough('header'),
  ElMain: passthrough('main'),
  ElMenu: passthrough('nav'),
  ElMenuItem: passthrough('button'),
  ElCard: passthrough('section'),
  ElRow: passthrough('div'),
  ElCol: passthrough('div'),
  ElButton: passthrough('button'),
  ElTag: passthrough('span'),
  ElTabs: passthrough('div'),
  ElTabPane: passthrough('section'),
  ElEmpty: passthrough('div'),
  ElAlert: passthrough('div'),
  ElSkeleton: passthrough('div'),
  ElSwitch: passthrough('label'),
  ElTooltip: passthrough('div'),
  ElTable: passthrough('table'),
  ElTableColumn: emptyStub('col', { role: 'presentation' }),
  ElIcon: passthrough('i'),
  ElDatePicker: passthrough('input'),
  ElDialog: passthrough('section'),
  Refresh: passthrough('span'),
}

config.global.directives = {
  loading: () => {},
}
