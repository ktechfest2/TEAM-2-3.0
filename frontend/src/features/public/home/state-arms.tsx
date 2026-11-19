const ARMS = [
  { name: 'FCT', src: '/images/arms/fct.png' },
  { name: 'Lagos', src: '/images/arms/lagos.png' },
  { name: 'Oyo', src: '/images/arms/oyo.png' },
  { name: 'Rivers', src: '/images/arms/rivers.png' },
  { name: 'Kano', src: '/images/arms/kano.png' },
] as const

export function StateArms() {
  return (
    <ul className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-2 sm:gap-x-8">
      {ARMS.map((arm) => (
        <li key={arm.name} className="leading-none">
          <img
            src={arm.src}
            alt={`${arm.name} coat of arms`}
            title={arm.name}
            width={44}
            height={44}
            className="block h-10 w-10 object-contain object-bottom opacity-80 grayscale contrast-110 transition hover:opacity-100 hover:grayscale-0 sm:h-11 sm:w-11"
          />
        </li>
      ))}
    </ul>
  )
}
