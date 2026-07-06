<template>
  <div
    class="trakt-stars"
    :class="{
      'trakt-stars--compact': compact,
      'trakt-stars--disabled': disabled,
      'trakt-stars--rated': Boolean(modelValue),
    }"
    data-testid="trakt-star-rating"
    @mouseleave="preview = null">
    <div class="trakt-stars__track" role="group" :aria-label="ariaLabel">
      <button
        v-for="index in 5"
        :key="index"
        type="button"
        class="trakt-stars__star"
        :disabled="disabled"
        :aria-label="`Rate ${index} out of 5 stars`"
        @mousemove="onMove(index, $event)"
        @click="onClick(index, $event)">
        <span class="trakt-stars__glyph trakt-stars__glyph--empty" aria-hidden="true">
          <i class="far fa-star"></i>
        </span>
        <span
          class="trakt-stars__glyph trakt-stars__glyph--fill"
          :style="{ width: `${fillPercent(index)}%` }"
          aria-hidden="true">
          <i class="fas fa-star"></i>
        </span>
      </button>
    </div>
    <span v-if="showValue && displayValue" class="trakt-stars__value">{{ displayValue }}</span>
  </div>
</template>

<script>
import { formatTraktStars } from '@/utils/traktRating.js';

export default {
  name: 'TraktStarRating',
  props: {
    modelValue: {
      type: [String, Number],
      default: '',
    },
    disabled: {
      type: Boolean,
      default: false,
    },
    compact: {
      type: Boolean,
      default: false,
    },
    showValue: {
      type: Boolean,
      default: false,
    },
    ariaLabel: {
      type: String,
      default: 'Rate on Trakt',
    },
  },
  emits: ['update:modelValue', 'rate'],
  data() {
    return {
      preview: null,
    };
  },
  computed: {
    effectiveValue() {
      if (this.preview != null) {
        return this.preview;
      }
      const current = Number(this.modelValue);
      return Number.isFinite(current) && current > 0 ? current : 0;
    },
    displayValue() {
      return formatTraktStars(this.modelValue);
    },
  },
  methods: {
    fillPercent(index) {
      const diff = this.effectiveValue - (index - 1);
      if (diff >= 1) {
        return 100;
      }
      if (diff >= 0.5) {
        return 50;
      }
      return 0;
    },
    valueFromEvent(index, event) {
      const rect = event.currentTarget.getBoundingClientRect();
      const isHalf = (event.clientX - rect.left) < rect.width / 2;
      return isHalf ? index - 0.5 : index;
    },
    onMove(index, event) {
      if (this.disabled) {
        return;
      }
      this.preview = this.valueFromEvent(index, event);
    },
    onClick(index, event) {
      if (this.disabled) {
        return;
      }
      const next = this.valueFromEvent(index, event);
      const current = this.modelValue ? Number(this.modelValue) : null;
      const cleared = current === next ? '' : String(next);
      this.preview = null;
      this.$emit('update:modelValue', cleared);
      this.$emit('rate', cleared);
    },
  },
};
</script>
